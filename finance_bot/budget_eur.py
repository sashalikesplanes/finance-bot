from beancount.core.data import (
    Entries,
    Transaction,
    create_simple_posting,
)

__plugins__ = ["budget_eur"]


def budget_eur(entries: Entries, options_map):
    return [budget_eur_entry(e) for e in entries], []


def budget_eur_entry(entry):
    if not isinstance(entry, Transaction):  # type: ignore
        return entry

    for posting in entry.postings:
        if posting.account.startswith("Income:") and posting.units.currency == "EUR":
            create_simple_posting(
                entry,
                "Income:Available",
                posting.units.number * -1,
                "BGT_EUR",
            )

            create_simple_posting(
                entry,
                posting.account,
                posting.units.number,
                "BGT_EUR",
            )

        if posting.account.startswith("Expenses:") and posting.units.currency == "EUR":
            create_simple_posting(
                entry,
                "Expenses:Spent",
                posting.units.number,
                "BGT_EUR",
            )

            create_simple_posting(
                entry,
                posting.account,
                posting.units.number * -1,
                "BGT_EUR",
            )

    return entry
