from decimal import Decimal
import sys
from beancount import loader
from beancount.query import query
from datetime import date
import calendar


def get_month_end(n_months_ahead):
    today = date.today()
    _, last_day = calendar.monthrange(today.year, today.month)
    last_date = date(today.year, today.month + n_months_ahead, last_day)
    return last_date


def generate_monthly_budget_report(entries, options):
    """
    Generate a monthly budget report for the current month.
    Sums up the allocated budget and the spent budget for each account based on currency and sign.
    Also sums up the income assigned to the budget.

    Args:
        entries (list): A list of entries from the Beancount file.
        options (dict): The options from the Beancount file.
            - filtered (bool): Whether to filter out fixed and savings expenses.
            - n_months_ahead (int): The number of months to look ahead for the budget report.

    Returns:
        list: A list of dictionaries representing the monthly budget report.
        Decimal: The total income assigned to the budget.
    """
    last_date = get_month_end(options["n_months_ahead"])

    # Query for budget allocations
    monthly_entries_query = f"""SELECT account, position, tags, date
    WHERE ((account ~ "Expenses:" and account != "Expenses:Spent") or account = "Income:Available")
      and date <= {last_date}
    """
    monthly_entries = query.run_query(entries, options, monthly_entries_query)

    accounts = {}
    income_assigned = Decimal(0)
    for row in monthly_entries[1]:
        if row.account == "Income:Available":
            income_assigned += row.position.units.number
            continue

        if row.account not in accounts:
            accounts[row.account] = {
                "assigned": Decimal(0),
                "assigned_this_month": Decimal(0),
                "spent": Decimal(0),
                "spent_this_month": Decimal(0),
                "account": row.account,
            }

        if (
            row.position is None
            or row.position.units is None
            or row.position.units.currency is None
        ):
            continue

        if row.position.units.currency == "EUR":
            accounts[row.account]["spent"] += row.position.units.number
            if row.date.month == last_date.month:
                accounts[row.account]["spent_this_month"] += row.position.units.number

        if (
            row.position.units.currency == "BGT_EUR"
            and row.position.units.number > 0
            and "budget" in row.tags
        ):
            accounts[row.account]["assigned"] += row.position.units.number
            if row.date.month == last_date.month:
                accounts[row.account][
                    "assigned_this_month"
                ] += row.position.units.number

    accounts = sorted(accounts.values(), key=lambda x: x["account"])
    if options["filtered"]:
        accounts = [
            account
            for account in accounts
            if not account["account"].startswith("Expenses:Fixed:")
            and not account["account"].startswith("Expenses:Savings:")
        ]
    # Iterate over the dictionary
    for account in accounts:
        account["account_name"] = account["account"].split(":")[2]
        account["remaining"] = account["assigned"] - account["spent"]
    return accounts, income_assigned, last_date


def main():
    filename = "main.beancount"
    entries, errors, options = loader.load_file(filename, log_errors=sys.stderr)

    options["filtered"] = True
    options["n_months_ahead"] = 0

    report = generate_monthly_budget_report(entries, options)
    print(report)


if __name__ == "__main__":
    main()
