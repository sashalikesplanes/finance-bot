ACCOUNTS = (
    "Assets:NL:ING:Checking59",
    "Assets:NL:ING:Checking34",
    "Assets:BE:WISE:Checking",
    "Assets:BE:WISE:Savings",
    "Assets:Cash",
    "Assets:BE:WISE:Investments",
    "Liabilities:NL:AMEX:Green",
    "Liabilities:NL:ING:CreditCard",
)

COUNTERPARTIES = {
    "Expenses:Variable": (
        "HouseTax",
        "Transport",
        "LuxTrip24Oct",
        "TurkeyTrip24Oct",
        "PersonalCare",
        "BankFees",
        "MyLove",
        "EatOut",
        "Tobacco",
        "Clothes",
        "Family",
        "Education",
        "Party",
        "Forgotten",
        "Groceries",
    ),
    "Expenses:Fixed": (
        "Phone",
        "Music",
        "Insurance",
        "Charity",
        "Fitness",
    ),
    "Income": ("NL:Fung:Salary", "Interest"),
    "Transfer": ACCOUNTS,
}


def get_accounts():
    return ACCOUNTS


def get_counterparties():
    return COUNTERPARTIES
