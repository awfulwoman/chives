import json
import pytest
from unittest.mock import MagicMock, patch
from chives.tools.registry import clear_registry


@pytest.fixture(autouse=True)
def reset():
    clear_registry()
    yield
    clear_registry()


def test_lookup_contact_by_name():
    mock_contact = MagicMock()
    mock_contact.givenName.return_value = "Alice"
    mock_contact.familyName.return_value = "Smith"
    mock_email = MagicMock()
    mock_email.value.return_value = "alice@example.com"
    mock_contact.emailAddresses.return_value = [mock_email]
    mock_contact.phoneNumbers.return_value = []

    Contacts_mock = MagicMock()
    mock_store = MagicMock()
    mock_store.unifiedContactsMatchingPredicate_keysToFetch_error_.return_value = (
        [mock_contact], None
    )
    Contacts_mock.CNContactStore.alloc.return_value.init.return_value = mock_store
    Contacts_mock.CNContact.predicateForContactsMatchingName_.return_value = MagicMock()
    Contacts_mock.CNContactGivenNameKey = "givenName"
    Contacts_mock.CNContactFamilyNameKey = "familyName"
    Contacts_mock.CNContactEmailAddressesKey = "emailAddresses"
    Contacts_mock.CNContactPhoneNumbersKey = "phoneNumbers"

    with patch.dict("sys.modules", {"Contacts": Contacts_mock}):
        import sys
        sys.modules.pop("chives.tools.contacts", None)
        import chives.tools.contacts as contacts
        contacts._cn_store = mock_store
        result = contacts.lookup_contact(name="Alice")
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "Alice Smith"
        assert "alice@example.com" in data[0]["emails"]
