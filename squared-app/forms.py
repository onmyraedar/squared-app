import phonenumbers

from flask_wtf import FlaskForm
from square.client import Client
from wtforms import IntegerField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Length

class PersonalDetailsForm(FlaskForm):
    name = StringField("Name",
        validators=[DataRequired(), Length(max=100)]
    )
    phone_number = StringField("10-digit Phone Number",
        validators=[DataRequired(), Length(min=10, max=11)],
        id="phoneNumberField"
    )
    submit = SubmitField("Continue",
        id="continueBtn"
    )

    def validate_phone(self, phone_number):
        number_details = phonenumbers.parse(phone_number.data)
        if not phonenumbers.is_valid_number(number_details):
            raise ValidationError("That phone number is invalid. Please try again.")

class LoyaltyForm(FlaskForm):
    submit = SubmitField("Continue to Payment",
        id="loyaltyToPaymentBtn"
    )

class ReferralForm(FlaskForm):
    has_referral_code = SelectField("Would you like to enter a referral code?",
        validators=[DataRequired()],
        id="referralYesNoField",
        choices=[
            ("Yes", "Yes, I have a referral code."),
            ("No", "No, I do not have a referral code.")
        ]
    )
    referral_code = StringField("Enter your referral code here:",
        validators=[Length(max=100)],
        id="referralCodeField"
    )
    wants_referral_group = SelectField("Would you like to join your ambassador's referral group and earn points together? (By agreeing to this, you also agree to create a loyalty account so we can track your progress.)",
        id="referralYesNoField",
        choices=[
            ("Yes", "Yes, I would like to join my ambassador's group."),
            ("No", "No, I would not like to join my ambassador's group.")
        ]
    )
    submit = SubmitField("Continue to Payment",
        id="referralsToPaymentBtn"
    )
