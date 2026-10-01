import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from hashlib import md5
from html import unescape

from dotenv import load_dotenv
load_dotenv()

import nh3
from flask import Flask, abort, render_template, redirect, url_for, flash, request, session
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from PIL import Image, ImageOps

from sqlalchemy import Integer, String, Text, DateTime, UniqueConstraint, event, func
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import generate_password_hash, check_password_hash

from forms import CreatePostForm, EditPostForm, CreateBlogForm, EditBlogForm, RegisterForm, LoginForm, CommentForm, AccountForm, PasswordForm, PhotoForm

from flask_login import (
    UserMixin,
    login_user,
    LoginManager,
    current_user,
    logout_user,
    login_required,
)

################### APP CONFIGURATION ###################

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get("FLASK_KEY", "dev-only-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DB_URI", "sqlite:///posts.db")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # uploads up to 5 MB
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")

Image.MAX_IMAGE_PIXELS = 25_000_000

ckeditor = CKEditor(app)
Bootstrap5(app)
csrf = CSRFProtect(app)  # every POST needs a CSRF token

for folder in ("avatars", "covers", "posts"):
    os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], folder), exist_ok=True)

################### FLASK-LOGIN ###################

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message_category = "warning"

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

################### DATABASE ###################

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
db.init_app(app)


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    """SQLite ignores foreign keys (and ON DELETE CASCADE) unless this is switched on."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def gravatar_url(email, size=200):
    """Gravatar for an email; 'identicon' gives every address a generated avatar if it has no Gravatar."""
    digest = md5(email.strip().lower().encode(), usedforsecurity=False).hexdigest()
    return f"https://www.gravatar.com/avatar/{digest}?s={size}&d=identicon&r=g"


# USER MODEL
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    profile_photo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    blogs = relationship("Blog", back_populates="owner", cascade="all, delete-orphan", passive_deletes=True, order_by="Blog.created_at.desc()")
    posts = relationship("Post", back_populates="author", cascade="all, delete-orphan", passive_deletes=True)
    comments = relationship("Comment", back_populates="comment_author", cascade="all, delete-orphan", passive_deletes=True)
    likes = relationship("PostLike", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)

    @property
    def avatar(self):
        """Uploaded photo if there is one, otherwise the Gravatar for the email (nothing extra is stored)."""
        if self.profile_photo:
            return url_for("static", filename=f"uploads/avatars/{self.profile_photo}")
        return gravatar_url(self.email)


# BLOG MODEL
class Blog(db.Model):
    __tablename__ = "blogs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    cover_image: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    owner_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    owner = relationship("User", back_populates="blogs")
    posts = relationship("Post", back_populates="blog", cascade="all, delete-orphan", passive_deletes=True, order_by="Post.created_at.desc()")

    @property
    def cover_url(self):
        return url_for("static", filename=f"uploads/covers/{self.cover_image}") if self.cover_image else None


# POST MODEL
class Post(db.Model):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(250), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    image: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    blog_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("blogs.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    blog = relationship("Blog", back_populates="posts")
    author = relationship("User", back_populates="posts")
    comments = relationship("Comment", back_populates="parent_post", cascade="all, delete-orphan", passive_deletes=True, order_by="Comment.created_at")
    likes = relationship("PostLike", back_populates="post", cascade="all, delete-orphan", passive_deletes=True)

    @property
    def image_url(self):
        return url_for("static", filename=f"uploads/posts/{self.image}") if self.image else None

    @property
    def read_minutes(self):
        return max(1, round(len(re.sub(r"<[^>]+>", " ", self.body).split()) / 200))


# LIKE MODEL (one row per user per post)
class PostLike(db.Model):
    __tablename__ = "post_likes"
    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_post_like"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    post_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    post = relationship("Post", back_populates="likes")
    user = relationship("User", back_populates="likes")


# COMMENT MODEL
class Comment(db.Model):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    post_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)

    comment_author = relationship("User", back_populates="comments")
    parent_post = relationship("Post", back_populates="comments")


with app.app_context():
    db.create_all()  # creates any missing tables; existing tables are left alone

################### HELPERS ###################

def save_image(file, folder, size, square=False):
    """Check an uploaded image, shrink it, store it as a JPEG and return the new filename."""
    try:
        img = ImageOps.exif_transpose(Image.open(file.stream))
        img.load()
    except (OSError, ValueError, Image.DecompressionBombError):
        raise ValueError("invalid image")

    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        background = Image.new("RGB", img.size, "white")
        background.paste(img, mask=img.getchannel("A"))
        img = background
    else:
        img = img.convert("RGB")

    if square:
        img = ImageOps.fit(img, size)
    else:
        img.thumbnail(size)

    filename = uuid.uuid4().hex + ".jpg"
    img.save(os.path.join(app.config["UPLOAD_FOLDER"], folder, filename), "JPEG", quality=85, optimize=True)
    return filename


def delete_image(folder, filename):
    if filename:
        path = os.path.join(app.config["UPLOAD_FOLDER"], folder, os.path.basename(filename))
        if os.path.exists(path):
            os.remove(path)


def upload(field, folder, size, current=None, remove=False, square=False):
    """Return the filename to store: a new upload, the current one, or None if removed. Raises ValueError for a bad image."""
    file = request.files.get(field)
    if file and file.filename:
        filename = save_image(file, folder, size, square)
        delete_image(folder, current)
        return filename
    if remove:
        delete_image(folder, current)
        return None
    return current


def flash_errors(form):
    for name, errors in form.errors.items():
        label = getattr(getattr(form, name, None), "label", None)
        for error in errors:
            flash(f"{label.text if label else name}: {error}", "danger")


def safe_next():
    """The ?next= page after login, only if it is a local path."""
    target = request.args.get("next")
    return target if target and target.startswith("/") and not target.startswith("//") else None


def blog_name_taken(name, exclude_id=0):
    return db.session.scalar(db.select(Blog.id).where(func.lower(Blog.name) == name.lower(), Blog.id != exclude_id)) is not None


@app.template_filter("fmt_date")
def fmt_date(value):
    return f"{value:%B} {value.day}, {value.year}"


@app.template_filter("fmt_datetime")
def fmt_datetime(value):
    return f"{value:%b} {value.day}, {value.year} at {value:%H:%M} UTC"


@app.template_filter("excerpt")
def excerpt(html, length=160):
    text = " ".join(unescape(nh3.clean(html, tags=set())).split())
    return text if len(text) <= length else text[:length].rsplit(" ", 1)[0] + "…"


@app.context_processor
def inject_year():
    return {"current_year": datetime.now().year}


@app.errorhandler(403)
@app.errorhandler(404)
def http_error(error):
    message = "You don't have permission to do that." if error.code == 403 else "We couldn't find that page."
    return render_template("error.html", code=error.code, message=message), error.code


@app.errorhandler(RequestEntityTooLarge)
def file_too_large(error):
    flash("That file is too large. The limit is 5 MB.", "danger")
    back = request.referrer or ""
    return redirect(back if back.startswith(request.host_url) else url_for("home"))

################### ROUTES ###################

# HOME
@app.route("/")
def home():
    """Landing page: recent and popular posts, publications and authors."""

    like_count = db.select(func.count(PostLike.id)).where(PostLike.post_id == Post.id).correlate(Post).scalar_subquery()

    recent_posts = db.session.scalars(db.select(Post).order_by(Post.created_at.desc()).limit(6)).all()
    popular_posts = db.session.scalars(db.select(Post).order_by(like_count.desc(), Post.views.desc()).limit(5)).all()
    popular_blogs = db.session.scalars(db.select(Blog).outerjoin(Post, Post.blog_id == Blog.id).group_by(Blog.id).order_by(func.count(Post.id).desc(), Blog.created_at.desc()).limit(6)).all()
    top_authors = db.session.scalars(db.select(User).join(Post, Post.author_id == User.id).group_by(User.id).order_by(func.count(Post.id).desc()).limit(8)).all()

    return render_template("home.html", recent_posts=recent_posts, popular_posts=popular_posts, popular_blogs=popular_blogs, top_authors=top_authors)


# ABOUT & CONTACT
@app.route("/about")
def about():
    """About page."""
    return render_template("about.html")


@app.route("/contact")
def contact():
    """Contact page."""
    return render_template("contact.html")


# AUTHENTICATION
@app.route("/login", methods=["GET", "POST"])
def login():
    """Login page."""

    if current_user.is_authenticated:
        return redirect(url_for("home"))

    form = LoginForm()

    if form.validate_on_submit():

        user = db.session.scalar(db.select(User).where(User.email == form.email.data.lower()))

        # one message for both cases, so the form doesn't reveal which emails are registered
        if not user or not check_password_hash(user.password, form.password.data):
            flash("Incorrect email or password.", "danger")
            return redirect(url_for("login", next=safe_next()))

        login_user(user)
        flash(f"Welcome back, {user.username}!", "success")

        return redirect(safe_next() or url_for("home"))

    return render_template("login.html", form=form)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register a new user."""

    if current_user.is_authenticated:
        return redirect(url_for("home"))

    form = RegisterForm()

    if form.validate_on_submit():

        email = form.email.data.lower()
        existing_user = db.session.scalar(db.select(User).where((User.email == email) | (func.lower(User.username) == form.username.data.lower())))

        if existing_user:
            if existing_user.email == email:
                flash("That email is already registered.", "danger")
            else:
                flash("That username is already taken.", "danger")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(form.password.data, method="pbkdf2:sha256", salt_length=16)

        new_user = User(username=form.username.data, email=email, password=hashed_password)

        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)
        flash("Welcome to Petals & Prose! Create your first blog to get started.", "success")

        return redirect(url_for("home"))

    return render_template("register.html", form=form)


@app.route("/logout")
@login_required
def logout():
    """Log the current user out."""

    logout_user()
    flash("You have been logged out.", "info")

    return redirect(url_for("home"))


# PROFILE (account settings)
@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """Current user's account settings: username and email (password and photo have their own routes below)."""

    form = AccountForm(obj=current_user)

    if form.validate_on_submit():
        username, email = form.username.data, form.email.data.lower()

        if db.session.scalar(db.select(User.id).where(func.lower(User.username) == username.lower(), User.id != current_user.id)):
            flash("That username is already taken.", "danger")
        elif db.session.scalar(db.select(User.id).where(User.email == email, User.id != current_user.id)):
            flash("That email is already registered.", "danger")
        else:
            current_user.username, current_user.email = username, email
            db.session.commit()
            flash("Account updated.", "success")
            return redirect(url_for("profile"))

    return render_template("profile.html", form=form, password_form=PasswordForm(), photo_form=PhotoForm())


@app.route("/profile/password", methods=["POST"])
@login_required
def change_password():
    """Change the current user's password."""

    form = PasswordForm()

    if not form.validate_on_submit():
        flash_errors(form)
    elif not check_password_hash(current_user.password, form.current_password.data):
        flash("Your current password is incorrect.", "danger")
    else:
        current_user.password = generate_password_hash(form.new_password.data, method="pbkdf2:sha256", salt_length=16)
        db.session.commit()
        flash("Password changed.", "success")

    return redirect(url_for("profile"))


@app.route("/profile/photo", methods=["POST"])
@login_required
def upload_photo():
    """Upload or replace the profile photo."""

    form = PhotoForm()

    if not form.validate_on_submit():
        flash_errors(form)
        return redirect(url_for("profile"))

    try:
        current_user.profile_photo = upload("photo", "avatars", (400, 400), current_user.profile_photo, square=True)
    except ValueError:
        flash("That file isn't a valid image.", "danger")
        return redirect(url_for("profile"))

    db.session.commit()
    flash("Profile photo updated.", "success")

    return redirect(url_for("profile"))


@app.route("/profile/photo/remove", methods=["POST"])
@login_required
def remove_photo():
    """Remove the uploaded photo, going back to the Gravatar."""

    delete_image("avatars", current_user.profile_photo)
    current_user.profile_photo = None
    db.session.commit()
    flash("Profile photo removed.", "info")

    return redirect(url_for("profile"))


@app.route("/profile/blogs")
@login_required
def my_blogs():
    """Display all blogs owned by the current user."""

    blogs = db.session.scalars(db.select(Blog).where(Blog.owner_id == current_user.id).order_by(Blog.id.desc())).all()

    return render_template("my_blogs.html", blogs=blogs)


# PUBLIC PROFILE
@app.route("/profile/<username>")
def public_profile(username):
    """View another user's public profile."""

    user = db.session.scalar(db.select(User).where(func.lower(User.username) == username.lower()))

    if not user:
        abort(404)

    posts = db.session.scalars(db.select(Post).where(Post.author_id == user.id).order_by(Post.created_at.desc()).limit(10)).all()

    return render_template("public_profile.html", user=user, posts=posts)


# BLOGS
@app.route("/blog/create", methods=["GET", "POST"])
@login_required
def create_blog():
    """Create a new blog."""

    form = CreateBlogForm()

    if form.validate_on_submit():

        if blog_name_taken(form.name.data):
            flash("A blog with that name already exists. Try another name.", "danger")
        else:
            try:
                cover = upload("cover_image", "covers", (1600, 1600))
            except ValueError:
                flash("That file isn't a valid image.", "danger")
            else:
                new_blog = Blog(name=form.name.data, description=form.description.data, cover_image=cover, owner=current_user)

                db.session.add(new_blog)
                db.session.commit()
                flash("Your blog is ready. Write your first post!", "success")

                return redirect(url_for("view_blog", blog_id=new_blog.id))

    return render_template("create_blog.html", form=form, is_edit=False)


@app.route("/blog/<int:blog_id>")
def view_blog(blog_id):
    """View a blog and all of its posts."""

    blog = db.get_or_404(Blog, blog_id)

    return render_template("blog.html", blog=blog, is_owner=current_user.is_authenticated and current_user.id == blog.owner_id)


@app.route("/blog/<int:blog_id>/edit", methods=["GET", "POST"])
@login_required
def edit_blog(blog_id):
    """Edit a blog (reuses create_blog.html)."""

    blog = db.get_or_404(Blog, blog_id)

    if blog.owner_id != current_user.id:
        abort(403)

    form = EditBlogForm(obj=blog)

    if form.validate_on_submit():

        if blog_name_taken(form.name.data, exclude_id=blog.id):
            flash("A blog with that name already exists. Try another name.", "danger")
        else:
            try:
                blog.cover_image = upload("cover_image", "covers", (1600, 1600), blog.cover_image, form.remove_cover.data)
            except ValueError:
                flash("That file isn't a valid image.", "danger")
            else:
                blog.name = form.name.data
                blog.description = form.description.data

                db.session.commit()
                flash("Blog updated.", "success")

                return redirect(url_for("view_blog", blog_id=blog.id))

    return render_template("create_blog.html", form=form, blog=blog, is_edit=True)


@app.route("/blog/<int:blog_id>/delete", methods=["POST"])
@login_required
def delete_blog(blog_id):
    """Delete a blog together with its posts, comments and likes."""

    blog = db.get_or_404(Blog, blog_id)

    if blog.owner_id != current_user.id:
        abort(403)

    delete_image("covers", blog.cover_image)
    for post in blog.posts:
        delete_image("posts", post.image)

    db.session.delete(blog)
    db.session.commit()
    flash("Blog deleted.", "info")

    return redirect(url_for("my_blogs"))


# POSTS
@app.route("/blog/<int:blog_id>/post/create", methods=["GET", "POST"])
@login_required
def create_post(blog_id):
    """Create a post inside a specific blog."""

    blog = db.get_or_404(Blog, blog_id)

    if blog.owner_id != current_user.id:
        abort(403)

    form = CreatePostForm()

    if form.validate_on_submit():
        try:
            image = upload("image", "posts", (1600, 1600))
        except ValueError:
            flash("That file isn't a valid image.", "danger")
        else:
            new_post = Post(title=form.title.data, subtitle=form.subtitle.data or None, body=nh3.clean(form.body.data), image=image, author=current_user, blog=blog)

            db.session.add(new_post)
            db.session.commit()
            flash("Post published.", "success")

            return redirect(url_for("view_post", post_id=new_post.id))

    return render_template("create_post.html", form=form, blog=blog, is_edit=False)


@app.route("/post/<int:post_id>")
def view_post(post_id):
    """View an individual post."""

    post = db.get_or_404(Post, post_id)

    is_author = current_user.is_authenticated and current_user.id == post.author_id
    is_owner = current_user.is_authenticated and current_user.id == post.blog.owner_id

    # count a view once per visitor session, and never the author's own visits
    viewed = session.get("viewed_posts", [])
    if post.id not in viewed and not is_author:
        post.views = Post.views + 1
        db.session.commit()
        session["viewed_posts"] = (viewed + [post.id])[-100:]

    liked = current_user.is_authenticated and any(like.user_id == current_user.id for like in post.likes)

    return render_template("post.html", post=post, form=CommentForm(), is_author=is_author, is_owner=is_owner, liked=liked)


@app.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def edit_post(post_id):
    """Edit a post (reuses create_post.html). Only its author can edit it."""

    post = db.get_or_404(Post, post_id)

    if post.author_id != current_user.id:
        abort(403)

    form = EditPostForm(obj=post)

    if form.validate_on_submit():
        try:
            post.image = upload("image", "posts", (1600, 1600), post.image, form.remove_image.data)
        except ValueError:
            flash("That file isn't a valid image.", "danger")
        else:
            post.title = form.title.data
            post.subtitle = form.subtitle.data or None
            post.body = nh3.clean(form.body.data)

            db.session.commit()
            flash("Post updated.", "success")

            return redirect(url_for("view_post", post_id=post.id))

    return render_template("create_post.html", form=form, blog=post.blog, post=post, is_edit=True)


@app.route("/post/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    """Delete a post. Its author or the owner of the blog can delete it."""

    post = db.get_or_404(Post, post_id)

    if current_user.id not in (post.author_id, post.blog.owner_id):
        abort(403)

    blog_id = post.blog_id

    delete_image("posts", post.image)
    db.session.delete(post)
    db.session.commit()
    flash("Post deleted.", "info")

    return redirect(url_for("view_blog", blog_id=blog_id))


# INTERACTIONS
@app.route("/post/<int:post_id>/like", methods=["POST"])
@login_required
def like_post(post_id):
    """Like a post, or unlike it if the user already liked it."""

    post = db.get_or_404(Post, post_id)

    like = db.session.scalar(db.select(PostLike).where(PostLike.post_id == post.id, PostLike.user_id == current_user.id))

    if like:
        db.session.delete(like)
    else:
        db.session.add(PostLike(post=post, user=current_user))

    try:
        db.session.commit()
    except IntegrityError:  # a double-click raced us; the unique constraint kept it to one like
        db.session.rollback()

    return redirect(url_for("view_post", post_id=post.id, _anchor="engage"))


@app.route("/post/<int:post_id>/comment", methods=["POST"])
@login_required
def add_comment(post_id):
    """Add a comment to a post."""

    post = db.get_or_404(Post, post_id)
    form = CommentForm()

    if form.validate_on_submit():

        new_comment = Comment(text=form.comment_text.data, comment_author=current_user, parent_post=post)

        db.session.add(new_comment)
        db.session.commit()

        return redirect(url_for("view_post", post_id=post.id, _anchor=f"comment-{new_comment.id}"))

    flash_errors(form)

    return redirect(url_for("view_post", post_id=post.id, _anchor="comments"))


@app.route("/comment/<int:comment_id>/delete", methods=["POST"])
@login_required
def delete_comment(comment_id):
    """Delete a comment. Its author or the owner of the blog can delete it."""

    comment = db.get_or_404(Comment, comment_id)

    if current_user.id not in (comment.author_id, comment.parent_post.blog.owner_id):
        abort(403)

    post_id = comment.post_id

    db.session.delete(comment)
    db.session.commit()
    flash("Comment deleted.", "info")

    return redirect(url_for("view_post", post_id=post_id, _anchor="comments"))


# RUN FLASK APP
if __name__ == "__main__":
    app.run(debug=True, port=5001)
