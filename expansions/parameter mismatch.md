### Deep Dive: Parameter Mismatch in Raw SQL (`Issue #1`)

Perhaps the most critical database interaction issue in this codebase is how it consistently uses placeholders that do not match the parameter dictionary keys during SQL execution. Below is a more detailed explanation of how this happens, why it breaks your updates, and how to correct it.

---

## Where the Mismatch Occurs

1. **`soft_delete` Method in `Chat`**
    ```python
    @classmethod
    def soft_delete(cls, chat_id: str) -> None:
        try:
            with db_session() as db:
                stmt = text("""
                    UPDATE chats
                    SET is_deleted = TRUE
                    WHERE id = :id
                """)
                db.execute(stmt, {"chat_id": chat_id})  # <-- Problem here
                db.commit()
        except Exception as e:
            logger.error(f"Failed to soft-delete chat {chat_id}: {e}")
            raise
    ```
    - The text query has `WHERE id = :id`, but your params pass `{"chat_id": chat_id}`. The query expects a parameter called `id`, which never gets a value. That typically means SQLAlchemy ends up seeing `NULL` or no bound parameter for `:id`, so it matches zero rows.

2. **`update_title` Method in `Chat`**
    ```python
    @classmethod
    def update_title(cls, chat_id: str, title: str) -> None:
        ...
        stmt = text("""
            UPDATE chats
            SET title = :title
            WHERE id = :id
        """)
        db.execute(stmt, {"title": cleaned_title, "chat_id": chat_id})  # <-- Same mismatch
        db.commit()
    ```
    - The placeholder `:id` is never bound; only `:title` is set. So this query silently updates zero rows.

3. **`update_model` Method in `Chat`**  
   Anywhere you see a snippet like:
   ```python
   stmt = text("""
       UPDATE chats
       SET model_id = :model_id
       WHERE id = :id
   """)
   db.execute(stmt, {"chat_id": chat_id, "model_id": model_id})
   ...
   ```
   - Again, you have `WHERE id = :id` but `chat_id` is the actual dictionary key.

In each case, the mismatch is that your query’s placeholder is `:id` (or `:some_column`), but the dictionary key you pass is something else, like `"chat_id"`. This mismatch means the query either:
- Binds `:id` to `None` or leaves it unbound, so no rows match.
- Fails the query if strict parameter binding is enabled (though typically it results in zero rows affected).

---

## Why This Is So Critical

- **Data Not Updated**: Because no rows match, your DB remains unchanged. For example, a “deleted” chat remains active in the DB, a “renamed” chat keeps its old title, etc.  
- **No Simple Error**: SQLAlchemy usually won’t raise a direct exception on an unbound parameter if the rest of the query is syntactically valid. It’ll just produce “0 rows updated.” This can silently break logic, leaving your program in an unexpected state.  
- **Hard to Detect**: If you rely on the code’s success logs (like “*Chat title updated*”), you may not realize the update never happened. Unless you check the row count or look at the DB directly, you might not see the mismatch.

---

## How to Correct It

### Option A: Align the Parameter Names in the Statement

If you prefer using `"chat_id"` in your Python dictionary:

```python
stmt = text("""
    UPDATE chats
    SET is_deleted = TRUE
    WHERE id = :chat_id
""")
db.execute(stmt, {"chat_id": chat_id})
```

Here, the query `WHERE id = :chat_id` matches the parameter dictionary’s key `chat_id`. This is often simpler if your code consistently uses `chat_id` for the parameter name.

### Option B: Use `"id"` as the Dictionary Key

Keep the query’s placeholder as `:id`, but make sure your dictionary references `id`:

```python
stmt = text("""
    UPDATE chats
    SET is_deleted = TRUE
    WHERE id = :id
""")
db.execute(stmt, {"id": chat_id})
```

This preserves the original query structure but changes the dictionary so that the parameter we pass in is named the same as the placeholder.

### Note on Consistency

Whichever pattern you choose, **be consistent** across all such updates. For instance, if you rename your placeholders to `:chat_id` in one part of `Chat`, make all `UPDATE` or `DELETE` statements in `Chat` use `:chat_id`; or vice versa. 

---

## Extra Advice

- **Check the Row Count**: If you do something like:
  ```python
  result = db.execute(...)
  updated_rows = result.rowcount
  if updated_rows == 0:
      # Possibly a mismatch or the row doesn't exist
  ```
  This helps catch silent mismatches.  

- **Use the ORM**: Doing something like:
  ```python
  chat = db.query(Chat).filter(Chat.id == chat_id).first()
  if chat:
      chat.is_deleted = True
  ```
  is often safer, since you avoid messing up placeholder names.  

- **Apply This Fix Everywhere**: Make sure you search the entire codebase for patterns like `WHERE id = :id` with `db.execute(... {"chat_id": chat_id} )` or any other mismatch. Correct them consistently.

---

### Summary

**Issue #1**—the parameter mismatch—causes your `UPDATE` (and possibly other) statements to do nothing because `:id` never receives the intended value. Fix it by aligning placeholders and dictionary keys:

```diff
- db.execute(stmt, {"chat_id": chat_id})
+ db.execute(stmt, {"id": chat_id})
  # or rename query placeholder to :chat_id
```

Completing that alignment is the single most important step to ensure your data actually changes. Once you fix these references, your `Chat` operations like `soft_delete`, `update_title`, etc., will function as intended.