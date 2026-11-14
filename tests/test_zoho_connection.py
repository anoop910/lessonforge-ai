
from app.config import settings
from app.llm.zoho_quickml import ZohoQuickMLChat


def main():

    required = {
        "ZOHO_QUICKML_URL": settings.ZOHO_QUICKML_URL,
        "ZOHO_QUICKML_KEY": settings.ZOHO_QUICKML_KEY,
        "ZOHO_ACCESS_TOKEN": settings.ZOHO_ACCESS_TOKEN,
        "ZOHO_CATALYST_ORG": settings.ZOHO_CATALYST_ORG,
    }

    missing = [
        name for name, value in required.items()
        if not value
    ]

    if missing:
        raise RuntimeError(
            f"Missing environment variables: {missing}"
        )

    llm = ZohoQuickMLChat(
        endpoint=settings.ZOHO_QUICKML_URL,
        endpoint_key=settings.ZOHO_QUICKML_KEY,
        access_token=settings.ZOHO_ACCESS_TOKEN,
        catalyst_org=settings.ZOHO_CATALYST_ORG,

        # Change these according to your
        # actual QuickML API JSON schema.
        input_field="messages",
        response_field="response",

        request_timeout=60
    )

    response = llm.invoke(
        "Explain RAG in simple English."
    )

    print("\nGenerated response:")
    print(response.content)


if __name__ == "__main__":
    main()
