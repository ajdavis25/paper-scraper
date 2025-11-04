from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length, Email


class PreferencesForm(FlaskForm):
    email = StringField("email", validators=[DataRequired(), Email()])
    keywords = StringField(
        "preferred topics (comma-separated)",
        validators=[DataRequired(), Length(min=2, max=200)]
    )
    submit = SubmitField("save preferences")
