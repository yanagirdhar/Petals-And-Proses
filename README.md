# Petals & Prose
#### Video Demo: https://youtu.be/HvWm6281tXw
#### Description:

**Petals & Prose** is a Substack-style blogging platform built with Python, Flask and SQLite. Anyone can register, create one or more *blogs* (think of them as publications, each with its own name, description and cover image), publish rich-text *posts* inside those blogs, and read, like and comment on other people's writing. Every writer gets a public profile, and the home page surfaces recent posts, popular posts, popular blogs and the most active authors, so a new visitor immediately sees what the community is writing.

I chose this project because it let me use almost everything CS50 taught across the second half of the course: Python for the back end, SQL for a properly relational data model, HTML/CSS/JavaScript (via Bootstrap) for the front end, and Flask to tie them together. I also wanted to build something I would actually use, so I treated security, permissions and usability as first-class features instead of afterthoughts.

## How to run it

```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py                                        # http://127.0.0.1:5001
```

Optional environment variables (loaded from a `.env` file): `FLASK_KEY` (the session secret) and `DB_URI` (defaults to SQLite at `instance/posts.db`). The tables are created automatically on startup, so a missing database simply gets recreated.

## Features

- **Accounts:** register, log in and log out. Passwords are hashed with PBKDF2-SHA256 and never stored in plain text. The login form shows one generic error for both a wrong email and a wrong password, so it can't be used to discover which emails are registered. The `?next=` redirect after login is only followed if it is a local path, which prevents open-redirect attacks.
- **Account settings (`/profile`):** change username and email, change password (requires the current one), and upload or remove a profile photo. If no photo is uploaded, the user's Gravatar is used, with a generated identicon as a fallback, and nothing extra is stored.
- **Blogs:** create, view, edit and delete blogs, each with an optional cover image. Blog names are unique, checked case-insensitively.
- **Posts:** a CKEditor rich-text editor, optional subtitle and header image, an automatic "min read" estimate, and a view counter that counts each visitor once per session and never counts the author's own visits.
- **Likes and comments:** one like per user per post (toggle on/off), plain-text comments, and moderation rights for the blog owner.
- **Public profiles (`/profile/<username>`):** a writer's recent posts and details.
- **Home page:** recent posts, popular posts (ordered by likes, then views), popular blogs and top authors, all computed with SQL aggregates.

## Files

- **`main.py`** is the heart of the application (about 770 lines). It contains the app configuration, Flask-Login setup, the SQLAlchemy models (`User`, `Blog`, `Post`, `PostLike`, `Comment`), the image-handling helpers, the Jinja filters and every route. Routes are grouped by purpose: home/about/contact, authentication, profile, blogs, posts and interactions (likes/comments).
- **`forms.py`** defines every Flask-WTF form: registration, login, account, password, photo, blog, post and comment forms. Edit forms subclass the create forms (for example `EditPostForm` extends `CreatePostForm` with a "remove image" checkbox), so validation rules live in exactly one place. Usernames are restricted to letters, numbers and underscores, and a small set of reserved names is blocked because they would clash with routes such as `/profile/blogs`.
- **`requirements.txt`** lists the dependencies (Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF, Bootstrap-Flask, Flask-CKEditor, Pillow, nh3 and others, plus gunicorn and a PostgreSQL driver for deployment).
- **`instance/posts.db`** is the SQLite database.
- **`templates/`** holds the Jinja templates. `layout.html` is the base template (navbar, flash messages, footer). `_macros.html` holds reusable pieces: avatar, post card, post row, blog card, profile tabs and a confirmation modal for destructive actions. The page templates are `home.html`, `login.html`, `register.html`, `profile.html`, `public_profile.html`, `my_blogs.html`, `blog.html`, `create_blog.html` (also used for editing), `post.html`, `create_post.html` (also used for editing), `about.html`, `contact.html` and `error.html` (shared by 403 and 404 pages).
- **`static/css/styles.css`** contains the custom styling layered on top of Bootstrap, driven by CSS variables for the palette (cream, gold, brown, sage, navy, cherry red) defined in `static/assets/colours.txt`. **`static/js/scripts.js`** is a placeholder; Bootstrap's own JavaScript handles the dropdowns, modals and alerts. **`static/assets/`** holds the logos, favicon and login/register banners, and **`static/uploads/`** stores user-uploaded avatars, covers and post images.

## Database design

```
users       id, username*, email*, password, profile_photo?, created_at
blogs       id, owner_id → users, name*, description, cover_image?, created_at
posts       id, blog_id → blogs, author_id → users, title, subtitle?, body, image?, views, created_at
post_likes  id, post_id → posts, user_id → users, created_at      UNIQUE(post_id, user_id)
comments    id, post_id → posts, author_id → users, text, created_at
```

(`*` = unique, `?` = nullable.) Every foreign key is `ON DELETE CASCADE`, and because SQLite ignores foreign keys by default, `main.py` switches them on with `PRAGMA foreign_keys=ON` on every connection. Deleting a blog therefore removes its posts, comments and likes in one step, and the application also deletes the matching image files from disk.

## Design choices and why I made them

**Separate `post_likes` table.** My first idea was a simple integer `likes` column on posts, but that can't stop one user liking the same post repeatedly. A separate table with a `UNIQUE(post_id, user_id)` constraint enforces one like per user at the database level, and the like route catches the `IntegrityError` that a double-click race could cause. The like count is simply the number of rows.

**Blogs as a layer between users and posts.** Instead of posts belonging directly to users, they belong to a blog, which belongs to a user. This mirrors how Substack works and lets one writer run several publications. It also made the permission model more interesting (see below).

**Permissions are checked on the server, every time.** Hiding a button is not security. Every edit or delete route loads the object and calls `abort(403)` unless the current user is allowed: only a blog's owner can edit it or add posts; only a post's author can edit it; the author *or* the blog owner can delete a post; a comment can be deleted by its author or the blog owner. Account routes always use `current_user` and never an id taken from the URL, so there is no way to edit someone else's account.

**Sanitising and validating user content.** Post bodies are rich HTML, so they are cleaned with `nh3` before being saved, which strips scripts and unsafe attributes. Comments are plain text. All POST requests are protected by CSRF tokens (`CSRFProtect`), and every destructive button opens a confirmation modal.

**Handling uploaded images safely.** Uploads are limited to 5 MB and to common image types, opened with Pillow (so a renamed non-image file is rejected), rotated according to EXIF data, flattened onto a white background if transparent, resized, and re-saved as JPEG under a random UUID filename. That means original filenames and embedded metadata are never trusted or exposed, and file size stays manageable. Avatars are cropped to a square.

**Gravatar instead of storing default avatars.** Computing a Gravatar URL from the email hash costs nothing to store and gives every user a sensible picture from day one.

**Keeping the code readable.** I deliberately avoided heavy abstractions and a large front-end framework. Bootstrap plus a small custom stylesheet was enough, and keeping the routes plain and well commented made the project easier to debug and extend.

## Limitations and future work

The tables are created with `db.create_all()`, which doesn't alter existing tables, so changing the models on a database with real data would call for Flask-Migrate. Uploaded files live on local disk, which is fine for development but would need persistent storage on hosts with an ephemeral filesystem. Natural next steps are following authors, search, tags, pagination on the home page and email verification.

## AI usage

As permitted for the final project, I used an AI assistant (Claude by Anthropic) as a helper while developing and refactoring parts of this project. The idea, the design decisions and the overall structure are my own, and the use of AI is cited in the comments of my code.
