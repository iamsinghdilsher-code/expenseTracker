# Graph Report - C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker  (2026-04-25)

## Corpus Check
- 15 files · ~27,649 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 381 nodes · 730 edges · 26 communities detected
- Extraction: 72% EXTRACTED · 28% INFERRED · 0% AMBIGUOUS · INFERRED: 201 edges (avg confidence: 0.79)
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
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]

## God Nodes (most connected - your core abstractions)
1. `get_db()` - 84 edges
2. `_detect_category()` - 23 edges
3. `_log_audit()` - 23 edges
4. `TestDetectCategory` - 20 edges
5. `register()` - 17 edges
6. `_get_user()` - 17 edges
7. `_parse_csv_statement()` - 16 edges
8. `_get_umbrella_id()` - 16 edges
9. `_extract_last_four()` - 14 edges
10. `_parse_receipt_text()` - 14 edges

## Surprising Connections (you probably didn't know these)
- `Tests for the expense dashboard, CRUD operations, and core business logic.` --uses--> `DuplicateExpenseError`  [INFERRED]
  C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\tests\test_expenses.py → C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\app.py
- `load_user()` --calls--> `get_db()`  [INFERRED]
  C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\app.py → C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\database\db.py
- `_match_payment_method()` --calls--> `get_db()`  [INFERRED]
  C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\app.py → C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\database\db.py
- `_build_category_tree()` --calls--> `get_category_tree()`  [INFERRED]
  C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\app.py → C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\database\db.py
- `_save_expense()` --calls--> `get_db()`  [INFERRED]
  C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\app.py → C:\Users\iamsi\OneDrive\Desktop\expense-tracker\expense-tracker\database\db.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.08
Nodes (49): add_expense(), add_expense_bulk(), add_expense_photo(), add_expense_statement(), add_payment_method(), admin_audit(), admin_budgets(), admin_confirm_expense() (+41 more)

### Community 1 - "Community 1"
Cohesion: 0.07
Nodes (13): DuplicateExpenseError, _save_expense(), Exception, _add(), _get_umbrella_id(), _get_user(), Tests for the expense dashboard, CRUD operations, and core business logic., TestAddExpense (+5 more)

### Community 2 - "Community 2"
Cohesion: 0.1
Nodes (11): _match_payment_method(), Return payment_method id if last_four matches a registered card in the umbrella., _add_pm(), _get_pm(), Tests for payment method CRUD and card-matching logic., A card registered in umbrella A should not match queries for umbrella B., TestAddPaymentMethod, TestDeletePaymentMethod (+3 more)

### Community 3 - "Community 3"
Cohesion: 0.11
Nodes (9): _extract_last_four(), _parse_text_statement(), Extract card last-4 digits from text (OCR output or transaction description)., Strip HTML tags and collapse whitespace for plain-text fallback., _strip_html(), Unit tests for pure parsing/detection helper functions in app.py.  These tests r, TestExtractLastFour, TestParseTextStatement (+1 more)

### Community 4 - "Community 4"
Cohesion: 0.11
Nodes (11): app(), auth_client(), login(), power_client(), Client with a normal user (alice@test.com) already registered and logged in., Client with alice@test.com registered and role elevated to 'power'., Flask app wired to a fresh per-test SQLite file., register() (+3 more)

### Community 5 - "Community 5"
Cohesion: 0.08
Nodes (5): Tests for registration, login, logout, and route-level access control., TestAccessControl, TestLogout, TestRegister, TestSwitchUmbrella

### Community 6 - "Community 6"
Cohesion: 0.19
Nodes (7): _get_umbrella_id(), _get_user(), _make_draft(), Tests for the admin dashboard, draft management, budgets, and user permissions., TestBudgetManagement, TestDraftManagement, TestInviteLinks

### Community 7 - "Community 7"
Cohesion: 0.15
Nodes (5): _bulk_post(), Tests for bulk import, CSV/text statement parsing endpoints, and draft status lo, _sample_expenses(), TestBulkImport, TestStatementEndpoint

### Community 8 - "Community 8"
Cohesion: 0.18
Nodes (2): _detect_category(), TestDetectCategory

### Community 9 - "Community 9"
Cohesion: 0.22
Nodes (7): _payload(), _post(), Tests for the email inbound webhook (Phase 9)., TestWebhookAttachments, TestWebhookAuth, TestWebhookBodyParsing, TestWebhookSenderResolution

### Community 10 - "Community 10"
Cohesion: 0.27
Nodes (3): _normalize_date(), Convert common date formats to YYYY-MM-DD for SQLite strftime compatibility., TestNormalizeDate

### Community 11 - "Community 11"
Cohesion: 0.3
Nodes (2): _parse_receipt_text(), TestParseReceiptText

### Community 12 - "Community 12"
Cohesion: 0.3
Nodes (2): _parse_csv_statement(), TestParseCsvStatement

### Community 13 - "Community 13"
Cohesion: 0.28
Nodes (8): _create_home_umbrella(), get_category_tree(), Insert default top-level categories for a new umbrella. No-op if already seeded., Create a 'Home' umbrella for user_id, add them as admin, seed categories. Return, Returns top-level categories with nested children for an umbrella., Set up default umbrella and categories for a newly registered user., _seed_categories(), seed_db()

### Community 14 - "Community 14"
Cohesion: 0.25
Nodes (1): TestAdminAccess

### Community 15 - "Community 15"
Cohesion: 0.39
Nodes (3): _parse_email_sender(), Return bare lowercase email address from 'Name <email>' or plain 'email' string., TestParseEmailSender

### Community 16 - "Community 16"
Cohesion: 0.67
Nodes (1): Phase 1 migration: populate umbrellas, umbrella_access, categories for existing

### Community 17 - "Community 17"
Cohesion: 1.0
Nodes (0): 

### Community 18 - "Community 18"
Cohesion: 1.0
Nodes (0): 

### Community 19 - "Community 19"
Cohesion: 1.0
Nodes (0): 

### Community 20 - "Community 20"
Cohesion: 1.0
Nodes (0): 

### Community 21 - "Community 21"
Cohesion: 1.0
Nodes (1): Requires both a valid session and an active umbrella context.

### Community 22 - "Community 22"
Cohesion: 1.0
Nodes (1): Insert default top-level categories for a new umbrella. No-op if already seeded.

### Community 23 - "Community 23"
Cohesion: 1.0
Nodes (1): Create a 'Home' umbrella for user_id, add them as admin, seed categories. Return

### Community 24 - "Community 24"
Cohesion: 1.0
Nodes (1): Returns top-level categories with nested children for an umbrella.

### Community 25 - "Community 25"
Cohesion: 1.0
Nodes (1): Insert sample expenses for a newly registered user.

## Knowledge Gaps
- **32 isolated node(s):** `Requires a logged-in Power User.`, `Requires both a valid session and an active umbrella context.`, `Extract card last-4 digits from text (OCR output or transaction description).`, `Return payment_method id if last_four matches a registered card in the umbrella.`, `Convert common date formats to YYYY-MM-DD for SQLite strftime compatibility.` (+27 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 17`** (1 nodes): `wsgi.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 18`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 19`** (1 nodes): `main.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 20`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 21`** (1 nodes): `Requires both a valid session and an active umbrella context.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 22`** (1 nodes): `Insert default top-level categories for a new umbrella. No-op if already seeded.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 23`** (1 nodes): `Create a 'Home' umbrella for user_id, add them as admin, seed categories. Return`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 24`** (1 nodes): `Returns top-level categories with nested children for an umbrella.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 25`** (1 nodes): `Insert sample expenses for a newly registered user.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_db()` connect `Community 0` to `Community 1`, `Community 2`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 9`, `Community 13`?**
  _High betweenness centrality (0.585) - this node is a cross-community bridge._
- **Why does `email_inbound_webhook()` connect `Community 0` to `Community 3`, `Community 12`, `Community 15`?**
  _High betweenness centrality (0.120) - this node is a cross-community bridge._
- **Why does `_detect_category()` connect `Community 8` to `Community 0`, `Community 3`, `Community 11`, `Community 12`?**
  _High betweenness centrality (0.094) - this node is a cross-community bridge._
- **Are the 81 inferred relationships involving `get_db()` (e.g. with `load_user()` and `_match_payment_method()`) actually correct?**
  _`get_db()` has 81 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `_detect_category()` (e.g. with `.test_gas_station()` and `.test_costco_gas()`) actually correct?**
  _`_detect_category()` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 14 inferred relationships involving `register()` (e.g. with `.test_toggle_normal_to_power()` and `.test_toggle_power_to_normal()`) actually correct?**
  _`register()` has 14 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Requires a logged-in Power User.`, `Requires both a valid session and an active umbrella context.`, `Extract card last-4 digits from text (OCR output or transaction description).` to the rest of the system?**
  _32 weakly-connected nodes found - possible documentation gaps or missing edges._