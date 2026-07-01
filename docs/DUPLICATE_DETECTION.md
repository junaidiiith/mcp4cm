# Duplicate Detection

Duplicate Detection helps find models that are likely copies, exports of the same model, or near-identical variants.
MCP4CM can run several detection methods in one job. Each method contributes evidence for candidate duplicate pairs; the
final result is based on voting and optional mandatory methods.

## Contrastive GNN

**Contrastive GNN** is independent of the Node2Vec graph-embedding method. It sentence-encodes each node's normalized
type/name text and each edge's relationship type, then trains an edge-aware message-passing graph encoder without labels.
Training uses two randomly augmented views of every graph (edge dropout and node-feature masking) with an NT-Xent
contrastive loss. The resulting L2-normalized graph vectors are compared with cosine similarity.

The trained vectors are cached at `.mcp4cm_embeddings/<dataset>/<model>/contrastive_gnn.npz`. The cache key includes
every graph, sentence model, and training setting, so it is invalidated whenever the corpus or configuration changes.
This makes the method suitable for a whole dataset, not for mixing separately trained datasets.

The command-line workflow is:

```bash
pip install -e '.[ml]'
python scripts/run_duplicate_detection.py modelset-uml-json --technique gnn --threshold 0.85
```

For larger corpora, start with the default 20 epochs and use `--gnn-batch-size` to bound memory. CUDA is selected when
available; use `--gnn-device cpu` for reproducible CPU-only execution. The web UI exposes the same training controls.

## General Workflow

1. Upload and parse a dataset.
2. Open **Duplicate Detection**.
3. Select one or more detection methods.
4. Configure method parameters.
5. Set the voting rules.
6. Run detection.
7. Review candidate pairs and duplicate groups.

The result is split into two review views:

- **Duplicate groups**: connected sets of models that are approved as duplicates.
- **Candidate pairs**: individual model pairs with the methods that voted for them.

## How Voting Works

Each selected method can vote for a pair of models. A pair is approved as a duplicate when:

- it has at least the configured **minimum votes**, and
- it includes every selected **mandatory** method.

For example, assume the selected methods are **Hash**, **TF-IDF**, and **Graph metrics**:


| Pair | Method votes          | Minimum votes | Mandatory methods | Result       |
| ---- | --------------------- | ------------- | ----------------- | ------------ |
| A-B  | Hash, TF-IDF          | 2             | none              | Approved     |
| A-C  | TF-IDF                | 2             | none              | Not approved |
| A-D  | TF-IDF, Graph metrics | 2             | Hash              | Not approved |
| A-E  | Hash, Graph metrics   | 2             | Hash              | Approved     |


Mandatory methods are useful when one method should act as a hard gate. For example, making **Hash** mandatory means a
pair must have an exact name-hash match even if other methods also find it similar.

## Duplicate Groups

Approved duplicate pairs are connected into groups. If `A-B` and `B-C` are approved, MCP4CM shows one group containing
`A`, `B`, and `C`, even when `A-C` was not directly approved.

Groups include confidence indicators:


| Confidence | Meaning                                                                                    |
| ---------- | ------------------------------------------------------------------------------------------ |
| `complete` | Every internal pair in the group is approved.                                              |
| `linked`   | The group is connected by approved pairs, but not every internal pair has direct evidence. |
| `weak`     | At least one approved link has only one method vote.                                       |
| `mixed`    | The group contains internal candidate pairs that were not approved.                        |


## Representative Model

Each duplicate group gets a proposed representative, also called the canonical model. MCP4CM chooses it automatically by:

1. largest graph size, based on nodes plus edges,
2. most named elements,
3. stable model id as a tie-breaker.

The representative is a review aid. It does not delete or merge models automatically.

## 1) Hashing

Hashing is the fastest and strictest duplicate detection method. It creates an exact fingerprint from the normalized node
names of each model. Models with the same fingerprint are grouped as duplicates.

Hashing is best for finding exact copies where the same model appears more than once, possibly with harmless differences
such as capitalization, surrounding whitespace, punctuation, or node order.

Hashing does **not** compare graph structure, edges, edge types, layout, file names, or model ids. Two models with the
same normalized node-name list will match even if their relationships differ.

### What Hashing Compares

For each model, MCP4CM:

1. reads every node name,
2. normalizes each name,
3. optionally combines each name with its node type,
4. sorts the resulting tokens,
5. optionally removes repeated tokens,
6. hashes the token list.

Normalization includes:

- trimming leading and trailing whitespace,
- splitting common identifier boundaries such as `CustomerOrder` into `customer order`,
- replacing `_`, `-`, and `.` with spaces,
- removing punctuation,
- lowercasing,
- collapsing repeated whitespace.

Example:


| Raw node name   | Normalized name  |
| --------------- | ---------------- |
| `Order`         | `order`          |
| `CUSTOMER`      | `customer`       |
| `CustomerOrder` | `customer order` |
| `customer_id`   | `customer id`    |


### Parameters


| Parameter               | UI label          | Type    | Default | Description                                                                                                        |
| ----------------------- | ----------------- | ------- | ------- | ------------------------------------------------------------------------------------------------------------------ |
| `hashIncludeTypes`      | Types             | Boolean | `false` | When enabled, Hashing compares normalized `name + type` pairs instead of names only.                               |
| `minNamedNodes`         | Min named nodes   | Integer | `0`     | Minimum number of hash tokens required before a model is included in Hashing. Values below `0` are treated as `0`. |
| `deduplicateNameTokens` | Deduplicate names | Boolean | `false` | When enabled, repeated identical hash tokens are collapsed before hashing.                                         |


Guidance:


| Parameter               | When to change it                                                                                                |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `hashIncludeTypes`      | Turn on when generic names appear across different element types, for example `id`, `name`, or `state`.          |
| `minNamedNodes`         | Increase to avoid matching tiny models with one or two common names.                                             |
| `deduplicateNameTokens` | Turn on when repeated labels are parser noise or modeling style noise; keep off when multiplicity is meaningful. |


### Examples

#### Default Hashing

Configuration:


| Parameter         | Value |
| ----------------- | ----- |
| Types             | Off   |
| Min named nodes   | `0`   |
| Deduplicate names | Off   |


Models:


| Model | Node names                  |
| ----- | --------------------------- |
| A     | `Order`, `Customer`, `id`   |
| B     | `order`, `CUSTOMER`, `Id`   |
| C     | `Invoice`, `Customer`, `id` |


Hash tokens:


| Model | Tokens                      |
| ----- | --------------------------- |
| A     | `customer`, `id`, `order`   |
| B     | `customer`, `id`, `order`   |
| C     | `customer`, `id`, `invoice` |


Result:

- A and B match.
- C does not match A or B.

#### Types On

Use **Types** when names alone are too broad and node types should matter.

Configuration:


| Parameter         | Value |
| ----------------- | ----- |
| Types             | On    |
| Min named nodes   | `0`   |
| Deduplicate names | Off   |


Models:


| Model | Nodes                                              |
| ----- | -------------------------------------------------- |
| A     | `Order: BusinessObject`, `Customer: BusinessActor` |
| B     | `Order: DataObject`, `Customer: BusinessActor`     |


Hash tokens:


| Model | Tokens                                                     |
| ----- | ---------------------------------------------------------- |
| A     | `customer<TAB>business actor`, `order<TAB>business object` |
| B     | `customer<TAB>business actor`, `order<TAB>data object`     |


Result:

- With **Types** off, A and B match because names are identical.
- With **Types** on, A and B do not match because `Order` has a different type.

#### Minimum Named Nodes

Use **Min named nodes** to ignore very small or weakly named models.

Configuration:


| Parameter         | Value |
| ----------------- | ----- |
| Types             | Off   |
| Min named nodes   | `2`   |
| Deduplicate names | Off   |


Models:


| Model | Hash tokens         | Considered? |
| ----- | ------------------- | ----------- |
| A     | `order`             | No          |
| B     | `order`             | No          |
| C     | `customer`, `order` | Yes         |
| D     | `customer`, `order` | Yes         |


Result:

- A and B are ignored by Hashing because each has only one named node.
- C and D match.

#### Deduplicate Names

Use **Deduplicate names** when repeated identical names should not affect the fingerprint.

Configuration:


| Parameter         | Value |
| ----------------- | ----- |
| Types             | Off   |
| Min named nodes   | `0`   |
| Deduplicate names | On    |


Models:


| Model | Node names                   | Tokens before deduplication  | Tokens after deduplication |
| ----- | ---------------------------- | ---------------------------- | -------------------------- |
| A     | `Order`, `Order`, `Customer` | `customer`, `order`, `order` | `customer`, `order`        |
| B     | `Order`, `Customer`          | `customer`, `order`          | `customer`, `order`        |


Result:

- With **Deduplicate names** off, A and B do not match.
- With **Deduplicate names** on, A and B match.

Note: **Min named nodes** is checked after the deduplication setting is applied. If repeated names are collapsed, the
effective named-node count may become smaller.

### Strengths

- Very fast on large datasets.
- Deterministic and reproducible.
- No external machine-learning dependencies.
- Easy to explain and audit.
- Strong evidence for exact duplicate copies when model names are meaningful.

### Limitations

- Finds exact normalized token matches only.
- Does not detect renamed duplicates.
- Does not compare relationships or graph shape.
- Can match structurally different models that use the same set of names.
- Can be noisy on placeholder-heavy models, for example models dominated by `Class1`, `Entity`, `todo`, or `sample`.

For best results, run dummy cleansing first or configure dummy filters before relying on Hashing for final review.

## 2) TF-IDF

TF-IDF is a near-duplicate detection method for models with similar names, types, and optional relationship vocabulary.
It turns each model into a text document, computes TF-IDF vectors, and compares every model pair with cosine similarity.

TF-IDF is best for finding copied or slightly edited models where most domain vocabulary is still shared, but exact Hashing
is too strict.

TF-IDF does **not** compare graph structure, layout, model ids, or source file names. It compares the configured text
features only. A high TF-IDF score means two models use very similar normalized vocabulary, not necessarily that their
relationships are identical.

### What TF-IDF Compares

For each model, MCP4CM:

1. extracts normalized node names, node types, and edge types according to the selected token mode,
2. joins those tokens into one model document,
3. builds a TF-IDF vocabulary across the dataset,
4. computes cosine similarity for every model pair,
5. reports pairs whose similarity is greater than or equal to the configured threshold.

Normalization is the same name normalization used by Hashing:

- trimming leading and trailing whitespace,
- splitting common identifier boundaries such as `CustomerOrder` into `customer order`,
- replacing `_`, `-`, and `.` with spaces,
- removing punctuation,
- lowercasing,
- collapsing repeated whitespace.

### Token Modes


| Token mode         | What it compares                                                       | Typical use                                                         |
| ------------------ | ---------------------------------------------------------------------- | ------------------------------------------------------------------- |
| `names`            | Normalized node names only.                                            | Broad near-duplicate search based on model vocabulary.              |
| `names_types_bag`  | Normalized node names, node types, and edge types as one bag of words. | More type-aware search that still allows flexible matching.         |
| `typed_name_pairs` | Each normalized node type and node name as one atomic pair token.      | Strict type/name binding comparison when names alone are ambiguous. |


Examples:


| Raw node                          | `names` token      | `names_types_bag` tokens             | `typed_name_pairs` token                     |
| --------------------------------- | ------------------ | ------------------------------------ | -------------------------------------------- |
| `Order: BusinessObject`           | `order`            | `order`, `business object`           | `type_business_object__name_order`           |
| `Customer Account: BusinessActor` | `customer account` | `customer account`, `business actor` | `type_business_actor__name_customer_account` |


### Parameters


| Parameter                  | UI label       | Type                  | Default  | Description                                                         |
| -------------------------- | -------------- | --------------------- | -------- | ------------------------------------------------------------------- |
| `tfidfTokenMode`           | Token mode     | String                | `names`  | Selects which text features are used.                               |
| `tfidfSimilarityThreshold` | Threshold      | Float from `0` to `1` | `0.9`    | Minimum cosine similarity required for TF-IDF to vote for a pair.   |
| `tfidfMaxFeatures`         | Max features   | Integer               | `50000`  | Maximum number of TF-IDF vocabulary features kept by scikit-learn.  |
| `minDf`                    | Min DF         | Integer or float      | `1`      | Minimum document frequency for a token to stay in the vocabulary.   |
| `ngramRange`               | N-gram min/max | Pair of integers      | `[1, 1]` | Adds token sequences such as unigrams and bigrams.                  |
| `stopwordsMode`            | Stopwords      | `none` or `english`   | `none`   | Optionally removes built-in English stopwords before vectorization. |


Guidance:


| Parameter                  | When to change it                                                                                                                                                   |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tfidfTokenMode`           | Start with `names`; use `names_types_bag` when types and edge labels should influence similarity; use `typed_name_pairs` when the type/name binding itself matters. |
| `tfidfSimilarityThreshold` | Raise it to reduce false positives; lower it to find weaker near-duplicates for manual review.                                                                      |
| `tfidfMaxFeatures`         | Keep the default unless memory usage is high or the dataset has extremely large vocabulary.                                                                         |
| `minDf`                    | Increase to remove one-off tokens; keep at `1` when rare domain terms are important duplicate evidence.                                                             |
| `ngramRange`               | Use `[1, 2]` when multi-token phrases such as `customer order` should carry more weight.                                                                            |
| `stopwordsMode`            | Use `english` only when English filler words dominate labels; keep `none` for multilingual or domain-specific datasets.                                             |


### Examples

#### Default TF-IDF

Configuration:


| Parameter    | Value    |
| ------------ | -------- |
| Token mode   | `names`  |
| Threshold    | `0.9`    |
| Max features | `50000`  |
| Min DF       | `1`      |
| N-gram range | `[1, 1]` |
| Stopwords    | `none`   |


Models:


| Model | Node names                       |
| ----- | -------------------------------- |
| A     | `Order`, `Customer`, `Invoice`   |
| B     | `order`, `Customer`, `Invoice`   |
| C     | `Payment`, `Customer`, `Account` |


Result:

- A and B have the same normalized name vocabulary and receive a very high score.
- C shares only part of the vocabulary, so its score against A or B is lower.

#### Lower Threshold

Use a lower threshold when near-duplicates may have several renamed or added elements.

Configuration:


| Parameter  | Value   |
| ---------- | ------- |
| Token mode | `names` |
| Threshold  | `0.7`   |


Models:


| Model | Node names                                |
| ----- | ----------------------------------------- |
| A     | `Order`, `Customer`, `Invoice`, `Address` |
| B     | `Order`, `Customer`, `Invoice`, `Payment` |


Result:

- With threshold `0.9`, A and B may not match because one element differs.
- With threshold `0.7`, TF-IDF is more likely to report A and B as a candidate pair.

Lower thresholds are useful for exploration, but they should usually be combined with another method or reviewed manually.

#### Names and Types Bag

Use `names_types_bag` when type and relationship vocabulary should affect similarity.

Configuration:


| Parameter  | Value             |
| ---------- | ----------------- |
| Token mode | `names_types_bag` |
| Threshold  | `0.9`             |


Models:


| Model | Nodes                                              | Edge type     |
| ----- | -------------------------------------------------- | ------------- |
| A     | `Order: BusinessObject`, `Customer: BusinessActor` | `Association` |
| B     | `Order: BusinessObject`, `Customer: BusinessActor` | `Flow`        |


Result:

- With `names`, A and B can look identical.
- With `names_types_bag`, the different edge type lowers the score.

#### Typed Name Pairs

Use `typed_name_pairs` when a name should only match strongly if it appears with the same node type.

Configuration:


| Parameter  | Value              |
| ---------- | ------------------ |
| Token mode | `typed_name_pairs` |
| Threshold  | `0.9`              |


Models:


| Model | Nodes                                              |
| ----- | -------------------------------------------------- |
| A     | `Order: BusinessObject`, `Customer: BusinessActor` |
| B     | `Order: BusinessActor`, `Customer: BusinessObject` |


TF-IDF pair tokens:


| Model | Tokens                                                                   |
| ----- | ------------------------------------------------------------------------ |
| A     | `type_business_object__name_order`, `type_business_actor__name_customer` |
| B     | `type_business_actor__name_order`, `type_business_object__name_customer` |


Result:

- With `names`, A and B match because the names are the same.
- With `names_types_bag`, A and B can still look very similar because the same names and types appear.
- With `typed_name_pairs`, A and B do not match strongly because the type/name bindings are swapped.

#### N-Grams

Use n-grams when token sequences should contribute additional evidence.

Configuration:


| Parameter    | Value    |
| ------------ | -------- |
| Token mode   | `names`  |
| N-gram range | `[1, 2]` |


Model names:


| Model | Node names                     |
| ----- | ------------------------------ |
| A     | `Customer Order`, `Invoice`    |
| B     | `Customer Order`, `Receipt`    |
| C     | `Customer`, `Order`, `Invoice` |


Result:

- A and B share the phrase-like token sequence `customer order`.
- C shares the words `customer` and `order`, but not necessarily the same combined phrase signal.

With `typed_name_pairs`, n-grams operate over atomic pair tokens, not words inside a pair. For example, the bigram may be:

`type_business_actor__name_customer type_business_object__name_order`

This means neighboring tokens in the sorted TF-IDF document, not adjacent nodes in the graph.

### Strengths

- Detects near-duplicates that exact Hashing misses.
- Deterministic and reproducible for the same dataset and parameters.
- Easy to tune with an intuitive similarity threshold.
- Useful as one voting signal together with Hashing or graph-based methods.
- Works across supported modeling languages because it consumes the normalized graph representation.

### Limitations

- Compares vocabulary, not graph structure.
- Can produce false positives when many models share common generic terms.
- Can miss renamed duplicates when the vocabulary changes substantially.
- Full pairwise comparison is expensive on large datasets.
- N-grams are based on token order in the TF-IDF document, not graph adjacency.
- `stopwordsMode=english` can remove useful terms in non-English or domain-specific datasets.

For best results, use TF-IDF as a candidate-generation method and review results with voting, mandatory methods, or graph
comparison when structural equality matters.

## 3) Graph Metrics

Graph Metrics is a near-duplicate detection method for models with similar graph-level structure and normalized model
vocabulary. It computes several similarity metrics for every model pair, combines them into one weighted score, and
votes for pairs whose score is greater than or equal to the configured threshold.

Graph Metrics is best for finding models that are not exact text matches but still have similar element names, element
types, relationship types, graph size, and graph shape.

Graph Metrics does **not** check exact graph isomorphism. It compares summary metrics, so two models can receive a high
score even when individual nodes and edges are not arranged identically. Use **Isomorphism** when exact structure matters.

### What Graph Metrics Compares

For each pair of models, MCP4CM computes:

1. normalized node-name overlap,
2. normalized node-type overlap,
3. normalized edge-type overlap,
4. degree-distribution similarity,
5. graph-size similarity,
6. graph-density similarity,
7. optionally, directed in-degree and out-degree distribution similarity.

The final score is a weighted average. Weights do not need to add up to `1`; MCP4CM divides by the sum of all configured
weights.

For example, these two configurations have the same relative effect:


| Node names | Node types | Edge types | Degree | Size   | Density |
| ---------- | ---------- | ---------- | ------ | ------ | ------- |
| `0.25`     | `0.20`     | `0.15`     | `0.15` | `0.15` | `0.10`  |
| `25`       | `20`       | `15`       | `15`   | `15`   | `10`    |


The default weights make node names the strongest single signal, while still allowing structural similarity to influence
the result.

### Metrics


| Metric               | What it means                                                                            |
| -------------------- | ---------------------------------------------------------------------------------------- |
| Node names           | Jaccard overlap of normalized node-name sets.                                            |
| Node types           | Jaccard overlap of normalized node-type sets.                                            |
| Edge types           | Jaccard overlap of normalized relationship-type sets.                                    |
| Degree histogram     | Cosine similarity of node-degree distributions.                                          |
| In-degree histogram  | Cosine similarity of incoming-degree distributions when **Directed metrics** is enabled. |
| Out-degree histogram | Cosine similarity of outgoing-degree distributions when **Directed metrics** is enabled. |
| Size                 | Average ratio similarity of node counts and edge counts.                                 |
| Density              | Similarity of graph density, based on edge count relative to possible edge count.        |


Jaccard overlap means:

```text
shared values / all distinct values
```

For example:

```text
{order, customer} vs {order, invoice}
= {order} / {order, customer, invoice}
= 1 / 3
= 0.33
```

### Parameters


| Parameter                | UI label                 | Type                  | Default | Description                                                                              |
| ------------------------ | ------------------------ | --------------------- | ------- | ---------------------------------------------------------------------------------------- |
| `graphSimilarity`        | Threshold                | Float from `0` to `1` | `0.85`  | Minimum weighted score required for Graph Metrics to vote for a pair.                    |
| `nodeNameJaccard`        | Node names               | Non-negative number   | `0.25`  | Weight for normalized node-name overlap.                                                 |
| `nodeTypeJaccard`        | Node types               | Non-negative number   | `0.20`  | Weight for normalized node-type overlap.                                                 |
| `edgeTypeJaccard`        | Edge types               | Non-negative number   | `0.15`  | Weight for normalized edge-type overlap.                                                 |
| `degreeHistogram`        | Degree histogram         | Non-negative number   | `0.15`  | Weight for overall degree-distribution similarity.                                       |
| `inDegreeHistogram`      | In-degree histogram      | Non-negative number   | `0.15`  | Weight for incoming-degree similarity when **Directed metrics** is enabled.              |
| `outDegreeHistogram`     | Out-degree histogram     | Non-negative number   | `0.15`  | Weight for outgoing-degree similarity when **Directed metrics** is enabled.              |
| `sizeSimilarity`         | Size                     | Non-negative number   | `0.15`  | Weight for node-count and edge-count similarity.                                         |
| `densitySimilarity`      | Density                  | Non-negative number   | `0.10`  | Weight for graph-density similarity.                                                     |
| `useDirectedMetrics`     | Directed metrics         | Boolean               | `false` | When enabled, in-degree and out-degree histograms are included in the weighted score.    |
| `normalizeParallelEdges` | Normalize parallel edges | Boolean               | `false` | When enabled, repeated edges with the same source, target, and type are compacted first. |


The weight fields are inside `graphWeights` in API payloads.

Guidance:


| Parameter                | When to change it                                                                                                                       |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------- |
| `graphSimilarity`        | Raise it to reduce false positives; lower it to review weaker structural or vocabulary similarity.                                      |
| `nodeNameJaccard`        | Increase when element names are meaningful and renamed models should be penalized.                                                      |
| `nodeTypeJaccard`        | Increase when element type consistency matters, for example distinguishing actors, objects, classes, tasks, and events.                 |
| `edgeTypeJaccard`        | Increase when relationship vocabulary should matter, for example `Association` vs `Flow` vs `Generalization`.                           |
| `degreeHistogram`        | Increase when graph shape matters more than exact names.                                                                                |
| `inDegreeHistogram`      | Increase when incoming relationship patterns are important in directed graphs.                                                          |
| `outDegreeHistogram`     | Increase when outgoing relationship patterns are important in directed graphs.                                                          |
| `sizeSimilarity`         | Increase to avoid matching small fragments with larger models.                                                                          |
| `densitySimilarity`      | Increase when sparse and dense models should be separated.                                                                              |
| `useDirectedMetrics`     | Turn on for directed languages or datasets where incoming and outgoing relationships have different meaning.                            |
| `normalizeParallelEdges` | Turn on when duplicate parallel relationships are export noise; keep off when repeated relationships represent meaningful multiplicity. |


At least one configured weight must be greater than `0`. A metric with weight `0` is ignored.

### Examples

#### Default Graph Metrics

Configuration:


| Parameter                | Value  |
| ------------------------ | ------ |
| Threshold                | `0.85` |
| Directed metrics         | Off    |
| Normalize parallel edges | Off    |


Default weights:


| Metric           | Weight |
| ---------------- | ------ |
| Node names       | `0.25` |
| Node types       | `0.20` |
| Edge types       | `0.15` |
| Degree histogram | `0.15` |
| Size             | `0.15` |
| Density          | `0.10` |


Models:


| Model | Nodes                                            | Edge types    |
| ----- | ------------------------------------------------ | ------------- |
| A     | `Order: Class`, `Customer: Class`, `id: Field`   | `Association` |
| B     | `Invoice: Class`, `Customer: Class`, `id: Field` | `Association` |


Intermediate metrics:

```text
node_name_jaccard            = 2 / 4 = 0.50
node_type_jaccard            = 1.00
edge_type_jaccard            = 1.00
degree_histogram_similarity  = 1.00
size_similarity              = 1.00
density_similarity           = 1.00
```

Weighted score:

```text
(0.25*0.50 + 0.20*1 + 0.15*1 + 0.15*1 + 0.15*1 + 0.10*1)
/ (0.25 + 0.20 + 0.15 + 0.15 + 0.15 + 0.10)
= 0.875
```

Result:

- With threshold `0.85`, A and B match.
- With threshold `0.90`, A and B do not match.

#### Name-Strict Configuration

Use higher node-name weight when renamed models should be less likely to match.

Configuration:


| Parameter  | Value  |
| ---------- | ------ |
| Threshold  | `0.85` |
| Node names | `0.60` |
| Node types | `0.10` |
| Edge types | `0.10` |
| Degree     | `0.10` |
| Size       | `0.05` |
| Density    | `0.05` |


With the same metrics as the previous example:

```text
(0.60*0.50 + 0.10*1 + 0.10*1 + 0.10*1 + 0.05*1 + 0.05*1)
/ 1.00
= 0.70
```

Result:

- A and B no longer match at threshold `0.85`.
- This configuration is useful when similar structure alone should not override different domain vocabulary.

#### Structure-Oriented Configuration

Use lower name weight and higher structural weights when names are noisy but graph shape is useful.

Configuration:


| Parameter        | Value  |
| ---------------- | ------ |
| Threshold        | `0.80` |
| Node names       | `0.10` |
| Node types       | `0.20` |
| Edge types       | `0.20` |
| Degree histogram | `0.25` |
| Size             | `0.15` |
| Density          | `0.10` |


Result:

- Models with different names can still match if they have similar types, relationship vocabulary, size, and shape.
- This is useful for exploratory review, but the results should usually be checked with the graph inspector or voting.

#### Directed Metrics

Use **Directed metrics** when edge direction should affect the score.

Models:


| Model | Relationships                           |
| ----- | --------------------------------------- |
| A     | `Customer -> Order`, `Order -> Invoice` |
| B     | `Order -> Customer`, `Invoice -> Order` |


Without directed metrics:

- A and B can look similar because the total degree distribution is the same.

With directed metrics:

- incoming and outgoing degree patterns are compared separately,
- the score can drop when the same relationships point in different directions.

This is useful for directed process, dependency, containment, or flow models where source and target roles matter.

#### Normalize Parallel Edges

Use **Normalize parallel edges** when repeated parallel relationships are export noise.

Models:


| Model | Relationships                                           |
| ----- | ------------------------------------------------------- |
| A     | one `Customer -> Order` edge with type `Association`    |
| B     | three `Customer -> Order` edges with type `Association` |


With **Normalize parallel edges** off:

- B has more edges,
- degree, size, and density metrics can differ,
- the score can be lower.

With **Normalize parallel edges** on:

- the repeated parallel edges are compacted into one edge for scoring,
- A and B are more likely to match.

Keep this setting off when repeated relationships represent meaningful multiplicity in the modeling language or dataset.

### Strengths

- Combines vocabulary and structural signals in one score.
- More flexible than exact Hashing.
- More graph-aware than TF-IDF.
- Deterministic and reproducible for the same dataset and parameters.
- Works without optional machine-learning dependencies.
- Useful as a balanced voting signal with Hashing, TF-IDF, or Isomorphism.

### Limitations

- Compares summary metrics, not exact node-to-node or edge-to-edge correspondence.
- Full pairwise comparison is expensive on large datasets.
- Jaccard metrics use distinct sets, so repeated names, types, and edge types do not increase overlap directly.
- High structural similarity can hide meaningful semantic differences when name/type weights are low.
- High name/type weights can hide structural differences when vocabulary is shared.
- Directed metrics only help when the parsed graph preserves meaningful edge direction.
- Parallel-edge normalization can hide meaningful multiplicity if repeated edges are intentional.

For best results, start with the default threshold and weights, inspect the highest-scoring pairs, then adjust weights
based on the type of false positives you see. Use Graph Metrics as a review and voting method, not as proof that two
models are exactly the same.


## 4) BERT

TODO: Verify implementation and add documentation
