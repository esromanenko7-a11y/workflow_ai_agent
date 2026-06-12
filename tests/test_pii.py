from app.observability.pii import prompt_hash, redact_pii


def test_redact_pii_masks_email_phone_and_card() -> None:
    raw_text = (
        "Мой email ivan@mail.ru, "
        "тел +7 (999) 123-45-67, "
        "карта 4111 1111 1111 1111"
    )

    redacted = redact_pii(raw_text)

    assert "[EMAIL]" in redacted
    assert "[PHONE_RU]" in redacted
    assert "[CARD]" in redacted

    assert "ivan@mail.ru" not in redacted
    assert "+7 (999) 123-45-67" not in redacted
    assert "4111 1111 1111 1111" not in redacted


def test_redact_pii_masks_inn_and_passport() -> None:
    raw_text = (
        "ИНН 7707083893, "
        "паспорт 45 10 123456"
    )

    redacted = redact_pii(raw_text)

    assert "[INN]" in redacted
    assert "[PASSPORT]" in redacted

    assert "7707083893" not in redacted
    assert "45 10 123456" not in redacted


def test_prompt_hash_does_not_expose_raw_prompt() -> None:
    raw_text = "Мой email ivan@mail.ru"

    hashed = prompt_hash(raw_text)

    assert hashed.startswith("sha256:")
    assert "ivan@mail.ru" not in hashed
    assert len(hashed) == len("sha256:") + 16