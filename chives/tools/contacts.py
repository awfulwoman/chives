from __future__ import annotations
import json
from chives.tools.registry import tool

_cn_store = None


def _get_store():
    global _cn_store
    if _cn_store is not None:
        return _cn_store
    import Contacts
    import threading

    store = Contacts.CNContactStore.alloc().init()
    done = threading.Event()

    def cb(granted, error):
        done.set()

    store.requestAccessForEntityType_completionHandler_(
        Contacts.CNEntityTypeContacts, cb
    )
    done.wait(timeout=10)
    _cn_store = store
    return store


@tool
def lookup_contact(name: str) -> str:
    """Look up a contact by name. Returns a list of matching contacts with email and phone."""
    import Contacts

    store = _get_store()
    keys = [
        Contacts.CNContactGivenNameKey,
        Contacts.CNContactFamilyNameKey,
        Contacts.CNContactEmailAddressesKey,
        Contacts.CNContactPhoneNumbersKey,
    ]
    pred = Contacts.CNContact.predicateForContactsMatchingName_(name)
    contacts, error = store.unifiedContactsMatchingPredicate_keysToFetch_error_(
        pred, keys, None
    )
    if error:
        return json.dumps({"error": str(error)})

    results = []
    for c in (contacts or []):
        emails = [str(e.value()) for e in (c.emailAddresses() or [])]
        phones = [str(p.value().stringValue()) for p in (c.phoneNumbers() or [])]
        results.append({
            "name": f"{c.givenName()} {c.familyName()}".strip(),
            "emails": emails,
            "phones": phones,
        })
    return json.dumps(results)
