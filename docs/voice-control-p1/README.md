# Voice Control P1

本目录保存供应商无关的语音识别与意图解析接口草案，不代表任何真实模型已经接入。

- [接口契约](interface-contract.md)
- [JSON Schema](contracts.schema.json)
- [正反例](fixtures.json)
- `validate_contracts.py`：离线校验 Schema 与样例，需要 Python `jsonschema`。

前端真实后端适配器默认关闭；后端评审并实现契约前，只能使用明确标记的本地 Mock。
