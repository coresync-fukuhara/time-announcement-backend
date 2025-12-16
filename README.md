JSON スキーマからモデルの生成

```
datamodel-codegen --input settings/schema.json --input-file-type jsonschema --output src/schedules_models.py --output-model-type pydantic_v2.BaseModel
```