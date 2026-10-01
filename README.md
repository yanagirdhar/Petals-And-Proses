# Petals & Prose

A simplified Substack-style blogging app built with Python + Flask: users, blogs (publications), posts, likes, comments, profiles.

## Run it

```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py                                        # http://127.0.0.1:5001
```

`instance/posts.db` is a fresh, empty database with the new schema. If it is ever missing or out of date, delete it and restart: the tables are recreated on startup (`db.create_all()`).

## Routes

| Route | What it does |
|---|---|
| `/`, `/about`, `/contact` | Home (recent + popular posts, blogs, writers), static pages |
| `/login`, `/register`, `/logout` | Authentication |
| `/profile` | Account settings: username, email |
| `/profile/password`, `/profile/photo`, `/profile/photo/remove` | Change password, upload or remove photo (POST only) |
| `/profile/blogs` | My blogs (with the Create Blog button) |
| `/profile/<username>` | Public profile |
| `/blog/create`, `/blog/<id>`, `/blog/<id>/edit`, `/blog/<id>/delete` | Create, view, edit, delete a blog |
| `/blog/<id>/post/create` | New post |
| `/post/<id>`, `/post/<id>/edit`, `/post/<id>/delete` | View, edit, delete a post |
| `/post/<id>/like` | Like / unlike (POST, toggles) |
| `/post/<id>/comment`, `/comment/<id>/delete` | Add / delete a comment (POST) |

## Database

```
users       id, username*, email*, password, profile_photo?, created_at
blogs       id, owner_id→users, name*, description, cover_image?, created_at
posts       id, blog_id→blogs, author_id→users, title, subtitle?, body, image?, views, created_at
post_likes  id, post_id→posts, user_id→users, created_at     UNIQUE(post_id, user_id)
comments    id, post_id→posts, author_id→users, text, created_at
```

`*` unique, `?` nullable. Every foreign key is `ON DELETE CASCADE` (SQLite foreign keys are switched on in `main.py`), so deleting a blog removes its posts, comments and likes. The like count is the number of `post_likes` rows.

## Who can do what

- **Profile / account**: only the logged-in user, and always their own (`current_user`, never an id from the URL).
- **Blog**: anyone can view; only the owner can edit, delete, or add posts.
- **Post**: anyone can view; only the author can edit; the author or the blog owner can delete.
- **Likes / comments**: logged-in users; one like per user per post; a comment can be deleted by its author or the blog owner.
- Every POST is CSRF-protected, and delete buttons ask for confirmation.

## Images and safety

- Profile photos, blog covers and post images are real uploads (jpg, png, gif, webp, up to 5 MB). They are checked with Pillow, resized, and saved as JPEG under `static/uploads/` with random filenames.
- No uploaded photo? The user's Gravatar (from their email) is used, with a generated identicon if they have none. Nothing is stored for that.
- Post bodies are sanitised with `nh3` when saved, so the rich text editor can't inject scripts. Comments are plain text.
- Uploaded files live on disk. On hosts with an ephemeral filesystem (Heroku-style) they disappear on redeploy; use persistent storage there.

## Later: schema changes

The tables are created with `db.create_all()`, which doesn't alter existing tables. When you start changing models on a database that holds real data, add Flask-Migrate (`pip install Flask-Migrate`, `Migrate(app, db)`, then `flask db init / migrate / upgrade`).
