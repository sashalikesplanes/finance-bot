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
    income_available = Decimal(0)
    for row in monthly_entries[1]:
        if row.account == "Income:Available":
            income_available += row.position.units.number
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

        if row.position.units.currency == "BGT_EUR" and "budget" in row.tags:
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

    table = f"Budget Report for {last_date.strftime('%B %Y')}\n\n"
    table += "<pre>\n"
    table += "| Account           | Assigned  | Available |\n"
    table += "|-------------------|----------:|----------:|\n"
    for account in accounts:
        table += f"| {account['account_name']:<17} | {account['assigned_this_month']:9.2f} | {account['remaining']:9.2f} |\n"
    table += "</pre>"
    if not options["filtered"]:
        table += f"Ready to assign: {income_available:9.2f} EUR\n"

    return table


def generate_account_report(entries, options):
    current_date = date.today()

    # Query for budget allocations
    current_accounts_query = f"""SELECT account, SUM(position) as position
    WHERE (account ~ "Assets:" or account ~ "Liabilities:")
      and date <= {current_date}
    """
    current_accounts = query.run_query(entries, options, current_accounts_query)

    accounts = []
    for row in current_accounts[1]:
        position = 0
        row_position = row.position.get_only_position()
        if row_position is not None:
            if row_position.units.currency != "EUR":
                raise ValueError(f"Unknown currency: {row_position.units.currency}")
            position = row_position.units.number

        account_name = row.account

        accounts.append({"account": account_name, "position": position})
    accounts = sorted(accounts, key=lambda x: x["account"])

    # make a table
    table = f"Account Report for {current_date}\n\n"
    table += "<pre>\n"
    table += "| Account                     | € Position |\n"
    table += "|-----------------------------|-----------:|\n"
    for account in accounts:
        table += f"| {account['account']:<27} | {account['position']:10.2f} |\n"
    table += "</pre>"

    return table


def main():
    filename = "main.beancount"
    entries, errors, options = loader.load_file(filename, log_errors=sys.stderr)

    report_type = sys.argv[1]

    if report_type == "budget":
        options["filtered"] = True
        options["n_months_ahead"] = 0

        report = generate_monthly_budget_report(entries, options)
        print(report)

    elif report_type == "account":
        report = generate_account_report(entries, options)
        print(report)
    else:
        raise ValueError(f"Unknown report type: {report_type}")


if __name__ == "__main__":
    main()
