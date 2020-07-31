#!/usr/bin/env python
# -*- coding: utf-8 -*-

import gnucashxml
import datetime
import logging
import collections
import decimal

def account_full_name(account):
    name = account.name
    parent = account.parent
    while parent.name != "Root Account":
        name = parent.name + ":" + name
        parent = parent.parent
    return name.encode("utf-8")


def check_splits_sanity(splits):
    if (len(splits) != 2):
        message = "check_splits_sanity ("
        for split in splits:
            message += "split (" + account_full_name(split.account) + ", " + \
                str(float(split.value)) + "), "
        message += ")"
        print message
        raise Exception(message)


def start(flux, name, i, periods):
    si = str(i)
    par = "(D" + si + ":" + column(periods) + si + ")"
    flux.write(name + ",=AVERAGE" + par + ",=SPARKLINE" + par)


def column(j):
    c = ''
    j += 4
    while j > 0:
        c = chr(ord('A') - 1 + + j % 26) + c
        j /= 26
    return c


class PeriodStr(object):
    def __init__(self, date):
        self.period_str = date.strftime("%Y-%m")

    def __eq__(self, obj):
        return self.period_str.__eq__(obj.period_str)

    def __lt__(self, obj):
        return self.period_str.__lt__(obj.period_str)

    def __le__(self, obj):
        return self.period_str.__le__(obj.period_str)

    def __gt__(self, obj):
        return self.period_str.__gt__(obj.period_str)

    def __ge__(self, obj):
        return self.period_str.__ge__(obj.period_str)

    def __hash__(self):
        return self.period_str.__hash__()

    def __int__(self):
        return int(self.period_str)

    def __str__(self):
        return self.period_str


class Assets(object):
    def __init__(self, assets_path):
        self.assets_path = assets_path
        self.assets = None

    def read_assets(self):
        self.assets = []
        with open(self.assets_path) as f:
            for line in f:
                asset = line.strip()
                if asset:
                    self.assets.append(asset)

    def is_asset(self, name):
        for asset in self.assets:
            if name.startswith(asset):
                return True
        return False


class Account(object):
    def __init__(self, name):
        self.name = name
        self.periods = {}

    def add_key(self, period):
        if period not in self.periods:
            self.periods[period] = 0

    def read_transaction(self, period, value):
        self.add_key(period)
        self.periods[period] += value

    def print_line(self, flux, periods, i):
        start(flux, self.name, i, len(periods))
        for period in sorted(periods):
            if period in self.periods:
                value = self.periods[period]
            else:
                value = 0
            flux.write("," + str(value))
        flux.write("\n")


class Periods(object):
    def __init__(self):
        self.periods = set()
        self.current_period = PeriodStr(datetime.date.today())

    def add_key(self, period):
        if period == self.current_period:
            return False
        logging.debug(
            "Periods.add_key: period (" + str(period) +
            ") < self.current_period (" + str(self.current_period) + ")")
        self.periods.add(period)
        return True

    def print_periods(self, flux):
        flux.write(",Average,Line")
        for period in sorted(self.periods):
            flux.write("," + str(period))
        flux.write("\n")

    def print_header(self, flux, pos, neg):
        self.print_periods(flux)
        self.print_sum(flux, "Total", 2, 0, pos + neg)
        self.print_sum(flux, "Positive", 3, 0, pos)
        self.print_sum(flux, "Negative", 4, pos, pos + neg)

    def print_sum(self, flux, name, i, begin, end):
        start(flux, name, i, len(self.periods))
        for j in range(len(self.periods)):
            c = column(j)
            flux.write(
                ",=SUM(" + c + str(5 + begin) + ":" + c + str(5 + end - 1) + ")")
        flux.write("\n")

    def print_percent(self, flux, name, num, den, i):
        start(flux, name, i, len(self.periods))
        for j in range(len(self.periods)):
            c = column(j)
            flux.write(",=" + c + str(num) + " / " + c + str(den))
        flux.write("\n")


class Table(object):
    def __init__(self, flux_path):
        self.flux_path = flux_path
        self.periods = Periods()
        self.pos = {}
        self.neg = {}

    def add_pos(self, account):
        logging.debug("Table.add_pos(" + account + ")")
        if account not in self.pos:
            self.pos[account] = Account(account)

    def add_neg(self, account):
        logging.debug("Table.add_neg(" + account + ")")
        if account not in self.neg:
            self.neg[account] = Account(account)

    def read_transaction(self, account, period, value):
        if not self.periods.add_key(period):
            return
        if value > 0:
            self.add_pos(account)
            self.pos[account].read_transaction(period, value)
        if value < 0:
            self.add_neg(account)
            self.neg[account].read_transaction(period, value)

    def print_accounts(self, flux):
        i = 5
        for account in sorted(self.pos):
            self.pos[account].print_line(flux, self.periods.periods, i)
            i += 1
        for account in sorted(self.neg):
            self.neg[account].print_line(flux, self.periods.periods, i)
            i += 1
        for account in sorted(self.pos):
            self.periods.print_percent(flux, account, i - len(self.pos) - len(self.neg), 3, i)
            i += 1
        for account in sorted(self.neg):
            self.periods.print_percent(flux, account, i - len(self.pos) - len(self.neg), 4, i)
            i += 1

    def print_table(self):
        with open(self.flux_path, "w") as flux:
            self.periods.print_header(flux, len(self.pos), len(self.neg))
            self.print_accounts(flux)



class Application(object):
    def __init__(self, gnucash_path, assets_path, flux_path):
        self.gnucash_path = gnucash_path
        self.assets = Assets(assets_path)
        self.table = Table(flux_path)

    def get_other_account(self, splits):
        logging.debug("get_other_account()")
        name_from = account_full_name(splits[0].account)
        name_to = account_full_name(splits[1].account)
        from_is_asset = self.assets.is_asset(name_from)
        to_is_asset = self.assets.is_asset(name_to)
        if from_is_asset and to_is_asset:
            logging.debug("Both assets: " + name_from + ", " + name_to)
            return None, None
        if from_is_asset:
            logging.debug("Asset: " + name_from + ", other: " + name_to)
            return name_to, 0
        if to_is_asset:
            logging.debug("Asset: " + name_to + ", other: " + name_from)
            return name_from, 1
        logging.debug("None are assets: " + name_from + ", " + name_to)
        return None, None

    def read_transaction(self, transaction):
        splits = transaction.splits
        check_splits_sanity(splits)
        account, i = self.get_other_account(splits)
        if account is None:
            return
        value = float(splits[i].value) / 12.0
        currency = transaction.currency.name
        if currency == "USD":
            value *= 3.1671
        elif currency == "EUR":
            value *= 3.9195
        period = PeriodStr(transaction.date)
        self.table.read_transaction(account, period, value)

    def main(self):
        book = gnucashxml.from_filename(self.gnucash_path)
        self.assets.read_assets()
        for transaction in book.transactions:
            self.read_transaction(transaction)
        self.table.print_table()

def main():
    logging.basicConfig(filename="flux.log", level=logging.DEBUG)
    app = Application("/home/marcots/gastos/gastos.gnucash", "assets.txt", "flux.csv")
    app.main()

if __name__ == "__main__":
    main()
