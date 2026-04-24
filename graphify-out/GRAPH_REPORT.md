# Graph Report - C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker  (2026-04-24)

## Corpus Check
- 5 files · ~13,773 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 45 nodes · 73 edges · 10 communities detected
- Extraction: 77% EXTRACTED · 23% INFERRED · 0% AMBIGUOUS · INFERRED: 17 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]

## God Nodes (most connected - your core abstractions)
1. `get_db()` - 14 edges
2. `_build_category_tree()` - 6 edges
3. `_save_expense()` - 6 edges
4. `seed_db()` - 6 edges
5. `init_db()` - 5 edges
6. `_detect_category()` - 4 edges
7. `register()` - 4 edges
8. `_create_home_umbrella()` - 4 edges
9. `_parse_receipt_text()` - 3 edges
10. `_parse_csv_statement()` - 3 edges

## Surprising Connections (you probably didn't know these)
- `load_user()` --calls--> `get_db()`  [INFERRED]
  C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\app.py → C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\database\db.py
- `_build_category_tree()` --calls--> `get_category_tree()`  [INFERRED]
  C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\app.py → C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\database\db.py
- `_save_expense()` --calls--> `get_db()`  [INFERRED]
  C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\app.py → C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\database\db.py
- `_save_expense()` --calls--> `seed_db()`  [INFERRED]
  C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\app.py → C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\database\db.py
- `register()` --calls--> `init_db()`  [INFERRED]
  C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\app.py → C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\database\db.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.24
Nodes (9): register(), _create_home_umbrella(), get_category_tree(), Create a 'Home' umbrella for user_id, add them as admin, seed categories. Return, Returns top-level categories with nested children for an umbrella., Insert sample expenses for a newly registered user., Insert default top-level categories for a new umbrella. No-op if already seeded., _seed_categories() (+1 more)

### Community 1 - "Community 1"
Cohesion: 0.28
Nodes (9): _build_category_tree(), delete_expense(), edit_expense(), expenses(), export_expenses(), load_user(), profile(), switch_umbrella() (+1 more)

### Community 2 - "Community 2"
Cohesion: 0.29
Nodes (0): 

### Community 3 - "Community 3"
Cohesion: 0.4
Nodes (5): add_expense(), add_expense_bulk(), login(), _save_expense(), init_db()

### Community 4 - "Community 4"
Cohesion: 0.67
Nodes (4): add_expense_statement(), _detect_category(), _parse_csv_statement(), _parse_text_statement()

### Community 5 - "Community 5"
Cohesion: 0.67
Nodes (3): add_expense_photo(), _allowed_image(), _parse_receipt_text()

### Community 6 - "Community 6"
Cohesion: 0.67
Nodes (1): Phase 1 migration: populate umbrellas, umbrella_access, categories for existing

### Community 7 - "Community 7"
Cohesion: 1.0
Nodes (2): Requires both a valid session and an active umbrella context., umbrella_required()

### Community 8 - "Community 8"
Cohesion: 1.0
Nodes (0): 

### Community 9 - "Community 9"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **6 isolated node(s):** `Requires both a valid session and an active umbrella context.`, `Insert default top-level categories for a new umbrella. No-op if already seeded.`, `Create a 'Home' umbrella for user_id, add them as admin, seed categories. Return`, `Returns top-level categories with nested children for an umbrella.`, `Insert sample expenses for a newly registered user.` (+1 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 7`** (2 nodes): `Requires both a valid session and an active umbrella context.`, `umbrella_required()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 8`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 9`** (1 nodes): `main.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_db()` connect `Community 1` to `Community 0`, `Community 3`?**
  _High betweenness centrality (0.142) - this node is a cross-community bridge._
- **Why does `seed_db()` connect `Community 0` to `Community 1`, `Community 3`?**
  _High betweenness centrality (0.108) - this node is a cross-community bridge._
- **Why does `_save_expense()` connect `Community 3` to `Community 0`, `Community 1`, `Community 2`?**
  _High betweenness centrality (0.070) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `get_db()` (e.g. with `load_user()` and `_build_category_tree()`) actually correct?**
  _`get_db()` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `_build_category_tree()` (e.g. with `get_db()` and `get_category_tree()`) actually correct?**
  _`_build_category_tree()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `_save_expense()` (e.g. with `get_db()` and `init_db()`) actually correct?**
  _`_save_expense()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `seed_db()` (e.g. with `register()` and `_save_expense()`) actually correct?**
  _`seed_db()` has 2 INFERRED edges - model-reasoned connections that need verification._