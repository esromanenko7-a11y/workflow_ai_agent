from app.tools.handlers import get_validation_report


def main():
    result = get_validation_report("PKG-001")

    print("Результат работы функции:")
    print(result)


if __name__ == "__main__":
    main()