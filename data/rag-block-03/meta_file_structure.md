# Проверка состава meta-файла

Код проверки: `META_FILE_STRUCTURE`
Категория: Проверка meta-файла
Критичность: ERROR

## Описание проверки

Проверяем наличие ключей внутри meta-файла:
- mask_file;
- params;
- schema_name;
- table_name;
- description;
- strategy;
- order;
- order_type;
- PK[];
- UK[];
- columns[].

## Цель

Проверить наличие обязательных ключей в составе meta-файла.

## Требования

- mask_file
- params
- schema_name
- table_name
- description
- strategy
- order
- order_type
- PK[]
- UK[]
- columns[]
