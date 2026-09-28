from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, SelectField, DateTimeLocalField,
    TextAreaField, BooleanField, FloatField, HiddenField,
)
from wtforms.validators import DataRequired, Optional, Length


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])


class BookingForm(FlaskForm):
    customer_name = StringField("Customer Name", validators=[DataRequired(), Length(max=120)])
    customer_contact = StringField("Contact", validators=[Optional(), Length(max=120)])
    service = StringField("Service", validators=[DataRequired(), Length(max=200)])
    scheduled_at = DateTimeLocalField("Scheduled Date & Time", validators=[DataRequired()], format="%Y-%m-%dT%H:%M")


class AcceptDeclineForm(FlaskForm):
    """A simple form with a hidden action field — no extra model needed."""
    pass


class RescheduleRequestForm(FlaskForm):
    new_time = DateTimeLocalField("New Date & Time", validators=[DataRequired()], format="%Y-%m-%dT%H:%M")
    reason = TextAreaField("Reason", validators=[Optional(), Length(max=500)])


class WalkInForm(FlaskForm):
    customer_name = StringField("Customer Name", validators=[DataRequired(), Length(max=120)])
    customer_contact = StringField("Contact", validators=[Optional(), Length(max=120)])
    service = StringField("Service", validators=[DataRequired(), Length(max=200)])
    scheduled_at = DateTimeLocalField("Scheduled Date & Time", validators=[DataRequired()], format="%Y-%m-%dT%H:%M")
    # Walk-in payment proof (handled outside, recorded here)
    payer_name = StringField("Payer Name", validators=[DataRequired(), Length(max=120)])
    payer_signature = TextAreaField("Payer Signature", validators=[DataRequired()])
    amount = FloatField("Amount Paid (cash)", validators=[Optional()])
