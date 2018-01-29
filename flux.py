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


class MonthStr(object):
    def __init__(self, date):
        self.month_str = date.strftime("%Y-%m")

    def __eq__(self, obj):
        return self.month_str.__eq__(obj.month_str)

    def __lt__(self, obj):
        return self.month_str.__lt__(obj.month_str)

    def __le__(self, obj):
        return self.month_str.__le__(obj.month_str)

    def __gt__(self, obj):
        return self.month_str.__gt__(obj.month_str)

    def __ge__(self, obj):
        return self.month_str.__ge__(obj.month_str)

    def __hash__(self):
        return self.month_str.__hash__()

    def __int__(self):
        fields = self.month_str.split('-')
        return int(fields[0]) * 12 + int(fields[1])

    def __str__(self):
        return self.month_str


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
        self.months = {}
        self.total = 0

    def add_key(self, month):
        if month not in self.months:
            self.months[month] = 0

    def read_transaction(self, month, value):
        self.add_key(month)
        self.months[month] += value
        self.total += value

    def num_months(self):
        return int(max(self.months)) - int(min(self.months)) + 1

    def print_line(self, flux, months):
        flux.write(self.name + "," + str(self.total / self.num_months()) + ",")
        for month in sorted(months):
            if month in self.months:
                value = self.months[month]
            else:
                value = 0
            flux.write(str(value) + ",")
        flux.write("\n")


class PositiveAccount(Account):
    def read_transaction(self, month, value):
        if value > 0:
            super(PositiveAccount, self).read_transaction(month, value)


class NegativeAccount(Account):
    def read_transaction(self, month, value):
        if value < 0:
            super(NegativeAccount, self).read_transaction(month, value)


class Months(object):
    def __init__(self):
        self.months = set()
        self.total = Account("Total")
        self.positive = PositiveAccount("Positive")
        self.negative = NegativeAccount("Negative")
        self.current_month = MonthStr(datetime.date.today())

    def add_key(self, month):
        self.months.add(month)

    def read_transaction(self, month, value):
        if month > self.current_month:
            return False
        logging.debug(
            "Months.read_transaction: month (" + str(month) +
            ") < self.current_month (" + str(self.current_month) + ")")
        self.add_key(month)
        self.total.read_transaction(month, value)
        self.positive.read_transaction(month, value)
        self.negative.read_transaction(month, value)
        return True

    def print_months(self, flux):
        flux.write(",Average,")
        for month in sorted(self.months):
            flux.write(str(month) + ",")
        flux.write("\n")

    def print_header(self, flux):
        self.print_months(flux)
        self.total.print_line(flux, self.months)
        self.positive.print_line(flux, self.months)
        self.negative.print_line(flux, self.months)


class Table(object):
    def __init__(self, flux_path):
        self.flux_path = flux_path
        self.months = Months()
        self.accounts = {}

    def add_key(self, account):
        logging.debug("Table.add_key(" + account + ")")
        if account not in self.accounts:
            self.accounts[account] = Account(account)

    def read_transaction(self, account, month, value):
        if not self.months.read_transaction(month, value):
            return
        self.add_key(account)
        self.accounts[account].read_transaction(month, value)

    def print_accounts(self, flux):
        for account in sorted(self.accounts):
            self.accounts[account].print_line(flux, self.months.months)

    def print_table(self):
        with open(self.flux_path, "w") as flux:
            self.months.print_header(flux)
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
        check_splits_sanity(transaction.splits)
        account, i = self.get_other_account(transaction.splits)
        if account is None:
            return
        value = float(transaction.splits[i].value)
        if transaction.currency.name == "USD":
            value *= 3.1671
        month = MonthStr(transaction.date)
        self.table.read_transaction(account, month, value)

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
