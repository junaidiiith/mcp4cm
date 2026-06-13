# Name Classification Test Contract

This document records the test contract for the shared name-classification
pipeline described in `docs/PIPELINE.md`. The implementation is shared by
statistics, dummy cleansing, and duplicate detection, so these fixtures guard
the behavior that downstream stages rely on.

The target behavior is intentionally small and stable:

- extract raw node names and types into `ExtractedLabel`;
- normalize names and types deterministically;
- tokenize normalized labels with a shared default tokenizer;
- classify node names as `missing`, `placeholder`, or `semantic`.

Examples are based on observed labels from:

- `eamodelset_ir_labels.json`
- `modelset-uml_ir_labels.json`
- existing Ecore IR fixtures

The examples below avoid testing the same behavior repeatedly. For example,
`approve order`, `initiate order`, and `create order` are all ordinary
multi-word semantic labels; one such case is enough.

## Test Subject

Golden assertions compare the full `ExtractedLabel` output:

```text
ExtractedLabel
  model_id
  element_id
  element_kind = "node"
  raw_name
  raw_type
  normalized_name
  normalized_type
  name_tokens
  type_tokens
  classification
```

Tests also call lower-level normalizer, tokenizer, and classifier functions
where that makes failures easier to diagnose. The composed extraction path must
stay aligned with those lower-level contracts.

## Default Configuration

Unless a test explicitly overrides configuration, the pipeline default is:

```yaml
normalizer:
  lowercase: true
  trim: true
  collapse_whitespace: true
  split_identifier_boundaries: true
tokenizer:
  split_camel_case: true
  keep_numeric_tokens: false
  min_token_length: 1
  deduplicate: false
  stopwords: []
classifier:
  classification_order:
    - missing
    - placeholder
    - semantic
```

Important distinction:

- `normalized_name` is a canonical string used for equality, display in
  analytical tables, and classification.
- `name_tokens` is the canonical token tuple used for vocabulary, TF-IDF,
  hashing variants, and dummy-cleansing vocabulary metrics.

Token order must be deterministic and must preserve occurrence order by
default. Deduplication is an explicit tokenizer option, not default behavior.

## Normalization Contract

Tests assert these rules directly and through `ExtractedLabel`.

| Raw Value | Expected Normalized | Purpose |
|---|---|---|
| ` Customer ` | `customer` | trim and lowercase |
| `Customer   Order` | `customer order` | collapse whitespace |
| `CustomerOrder` | `customer order` | PascalCase split |
| `creationDate` | `creation date` | camelCase split |
| `get_data` | `get data` | snake case split |
| `Real-time data acquisition` | `real time data acquisition` | punctuation split |
| `my.datatype` | `my datatype` | dotted identifier split |
| `OrderId` | `order id` | identifier suffix split |
| `userID` | `user id` | acronym suffix split |
| `PHP 7.x` | `php 7 x` | version punctuation normalized |
| `List<Order>` | `list order` | generic syntax normalized |
| `...` | `` | punctuation-only label becomes empty |
| `Gestão de SLA` | `gestão de sla` | accented Latin letters preserved |
| `退出與取回卡片` | `退出與取回卡片` | non-Latin label preserved |
| `Программист` | `программист` | Cyrillic label preserved and lowercased |

Decision:

- Version punctuation is normalized like other punctuation. `PHP 7.x` becomes
  `php 7 x`. With the default tokenizer, the numeric-only token is dropped, so
  the token tuple is `("php", "x")`. A stage that needs version numbers must
  opt into `keep_numeric_tokens: true`.

## Tokenizer Contract

Default tokenization consumes the normalized string.

| Normalized Value | Expected Tokens | Purpose |
|---|---|---|
| `` | `()` | empty input |
| `customer order` | `("customer", "order")` | ordinary semantic phrase |
| `creation date` | `("creation", "date")` | identifier-derived phrase |
| `order id` | `("order", "id")` | ID suffix kept as token |
| `php 7 x` | `("php", "x")` | numeric-only tokens dropped by default |
| `list order` | `("list", "order")` | generic syntax after normalization |
| `gestão de sla` | `("gestão", "de", "sla")` | Unicode words and acronym |
| `退出與取回卡片` | `("退出與取回卡片",)` | non-Latin token preserved |
| `customer customer` | `("customer", "customer")` | no default deduplication |

Configuration variant tests:

| Config Override | Input | Expected Tokens | Purpose |
|---|---|---|---|
| `keep_numeric_tokens: true` | `php 7 x` | `("php", "7", "x")` | explicit numeric retention |
| `deduplicate: true` | `customer customer order` | `("customer", "order")` | explicit deduplication |
| `min_token_length: 2` | `a b id` | `("id",)` | token-length filtering |
| `stopwords: ["de"]` | `gestão de sla` | `("gestão", "sla")` | explicit stopword filtering |

## Type Normalization Contract

Types are normalized and tokenized for downstream text/vector features. Tests
assert them separately so placeholder behavior is easy to diagnose.
Protected metamodel atoms such as Ecore classifier names remain unsplit; this
avoids noisy tokens such as `e` and prevents false overlap between Ecore
`EClass` and UML `Class`.

| Raw Type | Expected Normalized Type | Expected Type Tokens | Purpose |
|---|---|---|---|
| `Class` | `class` | `("class",)` | UML type |
| `DecisionNode` | `decision node` | `("decision", "node")` | UML control-node type |
| `ActivityFinalNode` | `activity final node` | `("activity", "final", "node")` | multi-token UML type |
| `BusinessProcess` | `business process` | `("business", "process")` | ArchiMate type |
| `Application Component` | `application component` | `("application", "component")` | already spaced type |
| `EClass` | `eclass` | `("eclass",)` | protected Ecore classifier atom |
| `EAttribute` | `eattribute` | `("eattribute",)` | protected Ecore structural feature atom |
| `EReference` | `ereference` | `("ereference",)` | protected Ecore reference atom |

The protected metamodel atom set is explicit configuration, not a broad change
to camel/Pascal splitting. It includes common Ecore atoms such as `EClass`,
`EAttribute`, `EReference`, `EPackage`, `EDataType`, and `EEnum`.

## Classification Contract

Classification order is fixed:

1. `missing`
2. `placeholder`
3. `semantic`

Type-derived names are included in placeholder classification. For example,
`Class` with type `Class`, `Class1` with type `Class`, and `ClassA` with type
`Class` are placeholders.

`placeholder` covers exact normalized type equivalence, numeric type indexes,
generic/generated low-information names, type-derived non-index variants, and
copied type labels such as `Junction (copy)`.

## ExtractedLabel Golden Cases

Each row is implemented as one node fixture and asserted as a full
`ExtractedLabel`.

| Case ID | Source Inspiration | Raw Name | Raw Type | Expected Normalized Name | Expected Normalized Type | Expected Name Tokens | Expected Type Tokens | Expected Classification | Behavior Covered |
|---|---|---|---|---|---|---|---|---|---|
| `missing-empty` | synthetic | `` | `Class` | `` | `class` | `()` | `("class",)` | `missing` | empty name |
| `missing-whitespace` | synthetic | `   ` | `Class` | `` | `class` | `()` | `("class",)` | `missing` | whitespace-only name |
| `missing-punctuation` | EA labels | `...` | `BusinessObject` | `` | `business object` | `()` | `("business", "object")` | `missing` | punctuation-only observed label |
| `type-exact` | UML labels | `InitialNode` | `InitialNode` | `initial node` | `initial node` | `("initial", "node")` | `("initial", "node")` | `placeholder` | exact placeholder name |
| `type-numbered-suffix` | UML labels | `DecisionNode2` | `DecisionNode` | `decision node2` | `decision node` | `("decision", "node2")` | `("decision", "node")` | `placeholder` | type plus index |
| `type-spaced-vs-camel` | EA labels | `Business Process` | `BusinessProcess` | `business process` | `business process` | `("business", "process")` | `("business", "process")` | `placeholder` | spacing/camel equivalence |
| `type-model-root` | UML labels | `model` | `Model` | `model` | `model` | `("model",)` | `("model",)` | `placeholder` | root/default model name |
| `placeholder-numbered-entity` | EA labels | `entity 1` | `BusinessObject` | `entity 1` | `business object` | `("entity",)` | `("business", "object")` | `placeholder` | generic numbered placeholder |
| `placeholder-numbered-class` | EA labels | `class 1` | `ApplicationComponent` | `class 1` | `application component` | `("class",)` | `("application", "component")` | `placeholder` | class placeholder with non-class type |
| `placeholder-operation-template` | UML labels | `privateOperation` | `Operation` | `private operation` | `operation` | `("private", "operation")` | `("operation",)` | `placeholder` | visibility-plus-kind generated name |
| `placeholder-attribute-template` | UML labels | `publicAttribute` | `Property` | `public attribute` | `property` | `("public", "attribute")` | `("property",)` | `placeholder` | generated attribute name |
| `placeholder-att-letter` | UML labels | `attB` | `Property` | `att b` | `property` | `("att", "b")` | `("property",)` | `placeholder` | short generated attribute pattern |
| `placeholder-type-letter-suffix` | synthetic | `ClassA` | `Class` | `class a` | `class` | `("class", "a")` | `("class",)` | `placeholder` | generic type name plus non-index suffix |
| `placeholder-copy-type-label` | EA labels | `Junction (copy)` | `Junction` | `junction copy` | `junction` | `("junction", "copy")` | `("junction",)` | `placeholder` | copied type label is low information |
| `semantic-pascal-domain` | UML labels | `ShoppingCart` | `Class` | `shopping cart` | `class` | `("shopping", "cart")` | `("class",)` | `semantic` | domain class |
| `semantic-camel-property` | UML labels | `creationDate` | `Property` | `creation date` | `property` | `("creation", "date")` | `("property",)` | `semantic` | domain property |
| `semantic-id-property` | EA labels | `OrderId` | `Property` | `order id` | `property` | `("order", "id")` | `("property",)` | `semantic` | ID suffix is domain-bearing |
| `semantic-snake-method` | UML labels | `get_data` | `Operation` | `get data` | `operation` | `("get", "data")` | `("operation",)` | `semantic` | snake-case operation |
| `semantic-generic-syntax` | UML labels | `List<Order>` | `Parameter` | `list order` | `parameter` | `("list", "order")` | `("parameter",)` | `semantic` | generic syntax keeps domain token |
| `semantic-version-tech` | EA labels | `PHP 7.x` | `TechnologyService` | `php 7 x` | `technology service` | `("php", "x")` | `("technology", "service")` | `semantic` | technology/version label |
| `semantic-accented` | EA labels | `Gestão de SLA` | `BusinessProcess` | `gestão de sla` | `business process` | `("gestão", "de", "sla")` | `("business", "process")` | `semantic` | accented Latin and acronym |
| `semantic-cyrillic` | EA labels | `Программист` | `BusinessRole` | `программист` | `business role` | `("программист",)` | `("business", "role")` | `semantic` | Cyrillic label |
| `semantic-cjk` | UML labels | `退出與取回卡片` | `Action` | `退出與取回卡片` | `action` | `("退出與取回卡片",)` | `("action",)` | `semantic` | CJK label |

## Classifier Unit Tests

Classifier tests isolate classification from extraction by passing
already-normalized names/types and token tuples.

Required edge cases:

| Normalized Name | Normalized Type | Name Tokens | Expected | Purpose |
|---|---|---|---|---|
| `` | `class` | `()` | `missing` | empty after normalization |
| `class` | `class` | `("class",)` | `placeholder` | exact type-derived placeholder |
| `class 2` | `class` | `("class",)` | `placeholder` | type with numeric index |
| `entity 1` | `business object` | `("entity",)` | `placeholder` | generic numbered placeholder |
| `aggregate 1` | `grouping` | `("aggregate",)` | `placeholder` | ArchiMate-style generated group |
| `class a` | `class` | `("class", "a")` | `placeholder` | generic type plus letter suffix |
| `junction copy` | `junction` | `("junction", "copy")` | `placeholder` | copied type label |
| `test` | `class` | `("test",)` | `placeholder` | keyword placeholder |
| `todo` | `action` | `("todo",)` | `placeholder` | keyword placeholder |
| `customer` | `class` | `("customer",)` | `semantic` | ordinary domain name |
| `name` | `property` | `("name",)` | `semantic` | common attribute name is not placeholder by itself |
| `id` | `property` | `("id",)` | `semantic` | common ID attribute is not missing or placeholder |

## Record-Level Golden Fixtures

These fixtures test aggregation behavior without requiring large real models.
They are built as small in-memory IR graphs or `ModelRecord` fixtures.

### Domain UML Fixture

Nodes:

| Raw Name | Raw Type | Expected Classification |
|---|---|---|
| `ShoppingCart` | `Class` | `semantic` |
| `LineItem` | `Class` | `semantic` |
| `creationDate` | `Property` | `semantic` |
| `OrderStatus` | `Enumeration` | `semantic` |

Expected aggregate behavior:

- semantic count is `4`;
- missing and placeholder counts are `0`;
- vocabulary includes `shopping`, `cart`, `line`, `item`, `creation`, `date`,
  `order`, and `status`;
- this fixture does not trigger dummy filters based on placeholder ratio or low
  vocabulary.

### UML Control-Node Fixture

Nodes:

| Raw Name | Raw Type | Expected Classification |
|---|---|---|
| `InitialNode` | `InitialNode` | `placeholder` |
| `DecisionNode2` | `DecisionNode` | `placeholder` |
| `MergeNode2` | `MergeNode` | `placeholder` |
| `ActivityFinalNode` | `ActivityFinalNode` | `placeholder` |

Expected aggregate behavior:

- placeholder count is `4`;
- semantic count is `0`;
- semantic-only text builders emit no name tokens;
- a model dominated by this fixture is low-information for dummy cleansing.

### Placeholder Fixture

Nodes:

| Raw Name | Raw Type | Expected Classification |
|---|---|---|
| `entity 1` | `BusinessObject` | `placeholder` |
| `class 1` | `ApplicationComponent` | `placeholder` |
| `aggregate 1` | `Grouping` | `placeholder` |
| `publicAttribute` | `Property` | `placeholder` |

Expected aggregate behavior:

- placeholder count is `4`;
- semantic count is `0`;
- placeholder ratio is `1.0`;
- dummy cleansing can remove a model dominated by this fixture.

### Multilingual Fixture

Nodes:

| Raw Name | Raw Type | Expected Classification |
|---|---|---|
| `Gestão de SLA` | `BusinessProcess` | `semantic` |
| `Téléphonies` | `ApplicationService` | `semantic` |
| `Программист` | `BusinessRole` | `semantic` |
| `退出與取回卡片` | `Action` | `semantic` |

Expected aggregate behavior:

- semantic count is `4`;
- no label is dropped by normalization or tokenization;
- normalized names preserve accented Latin, Cyrillic, and CJK characters.

## Cross-Stage Consistency Tests

The suite includes tests proving that downstream stages consume the same labels:

- statistics uses `ExtractedLabel.normalized_name`, `name_tokens`, and
  `classification` for node-label summaries;
- dummy cleansing uses the same labels for named counts, placeholder ratio, and
  vocabulary metrics;
- duplicate detection name/type methods use the same normalized names and types
  rather than reading raw graph attributes directly.

A single mixed fixture is enough:

| Raw Name | Raw Type | Expected Classification |
|---|---|---|
| `` | `Class` | `missing` |
| `InitialNode` | `InitialNode` | `placeholder` |
| `entity 1` | `BusinessObject` | `placeholder` |
| `ShoppingCart` | `Class` | `semantic` |
| `Gestão de SLA` | `BusinessProcess` | `semantic` |

Expected consistency:

- every stage sees exactly five node labels;
- classification counts are `missing=1`, `placeholder=2`, `semantic=2`;
- semantic-only token text includes tokens from `ShoppingCart` and
  `Gestão de SLA` only;
- all-name text excludes missing names but includes placeholder
  names only when the stage configuration explicitly asks for them.

## Non-Goals

- No stemming or lemmatization.
- No language detection.
- No generated-name classification beyond `placeholder`.
- No synonym handling.
- No parser-specific special cases unless they are explicitly added to the
  shared configuration and covered by golden tests.
- No edge-label classification in this document. Edge label profiling belongs
  in a separate test contract once `EdgeLabelProfile` is implemented.
