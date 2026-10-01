from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, SubmitField, PasswordField, TextAreaField, BooleanField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Regexp, ValidationError
from flask_ckeditor import CKEditorField

IMAGE_TYPES = ["jpg", "jpeg", "png", "gif", "webp"]
RESERVED_USERNAMES = {"blogs", "password", "photo"}  # would clash with /profile/<these>


def strip(value):
    return value.strip() if isinstance(value, str) else value


def not_reserved(form, field):
    if field.data.lower() in RESERVED_USERNAMES:
        raise ValidationError("That username is reserved.")


USERNAME_RULES = [DataRequired(), Length(3, 30), Regexp(r"^[A-Za-z0-9_]+$", message="Use only letters, numbers and underscores."), not_reserved]


# WTForm for creating a blog post
class CreatePostForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=250)], filters=[strip])
    subtitle = StringField("Subtitle (optional)", validators=[Length(max=250)], filters=[strip])
    image = FileField("Header image (optional)", validators=[FileAllowed(IMAGE_TYPES, "Images only (jpg, png, gif, webp).")])
    body = CKEditorField("Content", validators=[DataRequired()])
    submit = SubmitField("Publish Post")


# Same as above, plus the option to drop the current image
class EditPostForm(CreatePostForm):
    remove_image = BooleanField("Remove current header image")
    submit = SubmitField("Save Changes")


# WTForm for creating a blog
class CreateBlogForm(FlaskForm):
    name = StringField("Blog Name", validators=[DataRequired(), Length(max=150)], filters=[strip])
    description = TextAreaField("Description", validators=[DataRequired(), Length(max=500)], filters=[strip], render_kw={"rows": 3})
    cover_image = FileField("Cover Image (optional)", validators=[FileAllowed(IMAGE_TYPES, "Images only (jpg, png, gif, webp).")])
    submit = SubmitField("Create Blog")


# Create a form to edit a blog
class EditBlogForm(CreateBlogForm):
    remove_cover = BooleanField("Remove current cover image")
    submit = SubmitField("Save Changes")


# Create a form to register new users
class RegisterForm(FlaskForm):
    username = StringField("Username", validators=USERNAME_RULES, filters=[strip])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=100)], filters=[strip])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, message="Use at least 8 characters.")])
    confirm_password = PasswordField("Confirm Password", validators=[DataRequired(), EqualTo("password", message="Passwords must match.")])
    submit = SubmitField("Sign Me Up!")


# Create a form to login existing users
class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()], filters=[strip])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Let Me In!")


# Account settings: username + email
class AccountForm(FlaskForm):
    username = StringField("Username", validators=USERNAME_RULES, filters=[strip])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=100)], filters=[strip])
    submit = SubmitField("Save Changes")


# Account settings: password
class PasswordForm(FlaskForm):
    current_password = PasswordField("Current Password", validators=[DataRequired()])
    new_password = PasswordField("New Password", validators=[DataRequired(), Length(min=8, message="Use at least 8 characters.")])
    confirm_password = PasswordField("Confirm New Password", validators=[DataRequired(), EqualTo("new_password", message="Passwords must match.")])
    submit = SubmitField("Change Password")


# Account settings: profile photo
class PhotoForm(FlaskForm):
    photo = FileField("Profile Photo", validators=[FileRequired("Choose an image first."), FileAllowed(IMAGE_TYPES, "Images only (jpg, png, gif, webp).")])
    submit = SubmitField("Upload Photo")


# Create a form to add comments
class CommentForm(FlaskForm):
    comment_text = TextAreaField("Add a comment", validators=[DataRequired(), Length(max=2000)], filters=[strip], render_kw={"rows": 3, "placeholder": "Share your thoughts..."})
    submit = SubmitField("Post Comment")
