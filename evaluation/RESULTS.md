# Evaluation Results

## Dummy Detection

| Dataset | Filter | Models | Models (%) |
| :--- | :--- | ---: | ---: |
| ModelSet UML | Minimum size | 0 | 0.00 |
|  | Too few named elements | 59 | 1.15 |
|  | Short median name length | 192 | 3.75 |
|  | Placeholder-name ratio | 1,554 | 30.35 |
|  | Low vocabulary | 20 | 0.39 |
|  | Name-repetition ratio | 172 | 3.36 |
|  | Language | 859 | 16.78 |
| ModelSet Ecore | Minimum size | 122 | 2.26 |
|  | Too few named elements | 143 | 2.65 |
|  | Short median name length | 266 | 4.93 |
|  | Placeholder-name ratio | 84 | 1.56 |
|  | Low vocabulary | 50 | 0.93 |
|  | Name-repetition ratio | 53 | 0.98 |
|  | Language | 422 | 7.81 |
| EAModelSet | Minimum size | 20 | 2.08 |
|  | Too few named elements | 7 | 0.73 |
|  | Short median name length | 5 | 0.52 |
|  | Placeholder-name ratio | 72 | 7.49 |
|  | Low vocabulary | 3 | 0.31 |
|  | Name-repetition ratio | 4 | 0.42 |
|  | Language | 387 | 40.27 |
| SAP-SAM BPMN | Minimum size | 72 | 1.44 |
|  | Too few named elements | 275 | 5.50 |
|  | Short median name length | 243 | 4.86 |
|  | Placeholder-name ratio | 51 | 1.02 |
|  | Low vocabulary | 134 | 2.68 |
|  | Name-repetition ratio | 67 | 1.34 |
|  | Language | 2,221 | 44.42 |

## Dummy Detection Unions

| Dataset | Filter set | Removed | Remaining | Removed (%) |
| :--- | :--- | ---: | ---: | ---: |
| ModelSet UML | All enabled filters | 1,952 | 3,168 | 38.12 |
|  | Without language filter | 1,574 | 3,546 | 30.74 |
| ModelSet Ecore | All enabled filters | 660 | 4,740 | 12.22 |
|  | Without language filter | 404 | 4,996 | 7.48 |
| EAModelSet | All enabled filters | 462 | 499 | 48.07 |
|  | Without language filter | 91 | 870 | 9.47 |
| SAP-SAM BPMN | All enabled filters | 2,324 | 2,676 | 46.48 |
|  | Without language filter | 421 | 4,579 | 8.42 |

## Duplicate Detection

| Dataset | Technique | Models | Models (%) | Pairs | Groups | Largest group | Runtime |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| ModelSet UML | Hash | 2,493 | 48.69 | 73,573 | 382 | 177 | 12.32 s |
|  | TF-IDF | 3,645 | 71.19 | 130,815 | 424 | 238 | 20.16 s |
|  | Graph metrics | 3,583 | 69.98 | 129,243 | 434 | 233 | 158.35 s |
|  | BERT | 3,721 | 72.68 | 124,682 | 446 | 229 | 55.04 s |
|  | GNN | 3,752 | 73.28 | 107,687 | 496 | 218 | 45.48 s |
| ModelSet Ecore | Hash | 2,138 | 39.59 | 3,489 | 781 | 27 | 9.51 s |
|  | TF-IDF | 3,287 | 60.87 | 15,918 | 876 | 91 | 13.52 s |
|  | Graph metrics | 3,722 | 68.93 | 16,069 | 893 | 91 | 155.18 s |
|  | BERT | 3,729 | 69.06 | 19,213 | 846 | 101 | 48.95 s |
|  | GNN | 3,285 | 60.83 | 9,223 | 900 | 84 | 42.76 s |
| EAModelSet | Hash | 75 | 7.80 | 50 | 34 | 4 | 2.71 s |
|  | TF-IDF | 186 | 19.35 | 213 | 70 | 11 | 2.89 s |
|  | Graph metrics | 147 | 15.30 | 160 | 57 | 11 | 8.49 s |
|  | BERT | 155 | 16.13 | 154 | 62 | 9 | 4.47 s |
|  | GNN | 173 | 18.00 | 147 | 70 | 8 | 2.41 s |
| SAP-SAM BPMN | Hash | 1,848 | 36.96 | 173,531 | 73 | 266 | 4.02 s |
|  | TF-IDF | 2,019 | 40.38 | 174,604 | 96 | 267 | 10.19 s |
|  | Graph metrics | 2,054 | 41.08 | 175,385 | 100 | 269 | 99.66 s |
|  | BERT | 2,343 | 46.86 | 176,234 | 162 | 269 | 40.38 s |
|  | GNN | 2,068 | 41.36 | 175,148 | 129 | 268 | 38.44 s |
