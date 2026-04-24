# Graph Report - C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker  (2026-04-24)

## Corpus Check
- 4 files · ~8,045 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 29 nodes · 44 edges · 7 communities detected
- Extraction: 73% EXTRACTED · 27% INFERRED · 0% AMBIGUOUS · INFERRED: 12 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]

## God Nodes (most connected - your core abstractions)
1. `get_db()` - 10 edges
2. `_save_expense()` - 6 edges
3. `init_db()` - 5 edges
4. `register()` - 3 edges
5. `login()` - 3 edges
6. `add_expense_photo()` - 3 edges
7. `add_expense_statement()` - 3 edges
8. `load_user()` - 2 edges
9. `_allowed_image()` - 2 edges
10. `_parse_receipt_text()` - 2 edges

## Surprising Connections (you probably didn't know these)
- `load_user()` --calls--> `get_db()`  [INFERRED]
  C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\app.py → C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\database\db.py
- `_save_expense()` --calls--> `get_db()`  [INFERRED]
  C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\app.py → C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\database\db.py
- `_save_expense()` --calls--> `init_db()`  [INFERRED]
  C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\app.py → C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\database\db.py
- `_save_expense()` --calls--> `seed_db()`  [INFERRED]
  C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\app.py → C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\database\db.py
- `profile()` --calls--> `get_db()`  [INFERRED]
  C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\app.py → C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\database\db.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.28
Nodes (9): delete_expense(), edit_expense(), expenses(), load_user(), login(), profile(), register(), get_db() (+1 more)

### Community 1 - "Community 1"
Cohesion: 0.29
Nodes (0): 

### Community 2 - "Community 2"
Cohesion: 0.4
Nodes (4): add_expense(), add_expense_bulk(), _save_expense(), seed_db()

### Community 3 - "Community 3"
Cohesion: 0.67
Nodes (3): add_expense_photo(), _allowed_image(), _parse_receipt_text()

### Community 4 - "Community 4"
Cohesion: 0.67
Nodes (3): add_expense_statement(), _parse_csv_statement(), _parse_text_statement()

### Community 5 - "Community 5"
Cohesion: 1.0
Nodes (0): 

### Community 6 - "Community 6"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **Thin community `Community 5`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 6`** (1 nodes): `main.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_db()` connect `Community 0` to `Community 2`?**
  _High betweenness centrality (0.101) - this node is a cross-community bridge._
- **Why does `_save_expense()` connect `Community 2` to `Community 0`, `Community 1`?**
  _High betweenness centrality (0.096) - this node is a cross-community bridge._
- **Why does `register()` connect `Community 0` to `Community 1`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `get_db()` (e.g. with `load_user()` and `_save_expense()`) actually correct?**
  _`get_db()` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `_save_expense()` (e.g. with `get_db()` and `init_db()`) actually correct?**
  _`_save_expense()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `init_db()` (e.g. with `register()` and `login()`) actually correct?**
  _`init_db()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `register()` (e.g. with `init_db()` and `get_db()`) actually correct?**
  _`register()` has 2 INFERRED edges - model-reasoned connections that need verification._