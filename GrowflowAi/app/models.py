from datetime import date, datetime
from decimal import Decimal

from .extensions import bcrypt, db


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class User(TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    supabase_uid = db.Column(db.String(80), unique=True, nullable=True, index=True)
    auth_provider = db.Column(db.String(20), nullable=False, default="local")
    role = db.Column(db.String(20), nullable=False, default="owner")
    password_hash = db.Column(db.String(255), nullable=False)

    employees = db.relationship(
        "Employee",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan",
    )
    customers = db.relationship(
        "Customer",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan",
    )
    marketing_logs = db.relationship(
        "MarketingLog",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan",
    )
    subscriptions = db.relationship(
        "Subscription",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan",
    )
    settings_entries = db.relationship(
        "Setting",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan",
    )
    api_keys = db.relationship(
        "ApiKey",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan",
    )
    whatsapp_setting = db.relationship(
        "WhatsAppSetting",
        backref="user",
        uselist=False,
        lazy=True,
        cascade="all, delete-orphan",
    )
    whatsapp_messages = db.relationship(
        "WhatsAppMessage",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan",
    )
    whatsapp_templates = db.relationship(
        "WhatsAppTemplate",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan",
    )

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "auth_provider": self.auth_provider,
            "role": self.role,
        }


class Employee(TimestampMixin, db.Model):
    __tablename__ = "employees"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(120), nullable=False)

    attendance_records = db.relationship(
        "Attendance",
        backref="employee",
        lazy=True,
        cascade="all, delete-orphan",
    )

    def to_dict(self):
        latest_record = (
            sorted(self.attendance_records, key=lambda record: record.date, reverse=True)[0]
            if self.attendance_records
            else None
        )
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "role": self.role,
            "latest_status": latest_record.status if latest_record else "unmarked",
        }


class Attendance(db.Model):
    __tablename__ = "attendance"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(
        db.Integer,
        db.ForeignKey("employees.id"),
        nullable=False,
        index=True,
    )
    date = db.Column(db.Date, default=date.today, nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="present")
    marked_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("employee_id", "date", name="uniq_employee_date"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "employee_name": self.employee.name if self.employee else None,
            "date": self.date.isoformat(),
            "status": self.status,
        }


class Customer(TimestampMixin, db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(25), nullable=False)
    email = db.Column(db.String(255), nullable=True)

    invoices = db.relationship(
        "Invoice",
        backref="customer",
        lazy=True,
        cascade="all, delete-orphan",
    )
    whatsapp_messages = db.relationship(
        "WhatsAppMessage",
        backref="customer",
        lazy=True,
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "phone": self.phone,
            "email": self.email or "",
        }


class Invoice(TimestampMixin, db.Model):
    __tablename__ = "invoices"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(
        db.Integer,
        db.ForeignKey("customers.id"),
        nullable=False,
        index=True,
    )
    amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="pending")
    issued_on = db.Column(db.Date, default=date.today, nullable=False)

    def to_dict(self):
        amount = float(self.amount) if isinstance(self.amount, Decimal) else self.amount
        return {
            "id": self.id,
            "customer_id": self.customer_id,
            "customer_name": self.customer.name if self.customer else None,
            "amount": amount,
            "status": self.status,
            "issued_on": self.issued_on.isoformat(),
        }


class MarketingLog(db.Model):
    __tablename__ = "marketing_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    audience = db.Column(db.String(120), nullable=False, default="customers")
    delivery_status = db.Column(db.String(20), nullable=False, default="queued")
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "message": self.message,
            "audience": self.audience,
            "delivery_status": self.delivery_status,
            "sent_at": self.sent_at.isoformat(),
        }


class Subscription(TimestampMixin, db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    plan = db.Column(db.String(80), nullable=False, default="free")
    status = db.Column(db.String(20), nullable=False, default="active")
    renewed_on = db.Column(db.Date, default=date.today, nullable=False)
    trial_start_date = db.Column(db.Date, nullable=True)
    trial_end_date = db.Column(db.Date, nullable=True)
    promo_code_used = db.Column(db.String(80), nullable=True)
    promo_discount_percent = db.Column(db.Integer, nullable=False, default=0)
    promo_discount_amount = db.Column(db.Integer, nullable=False, default=0)
    amount_due = db.Column(db.Integer, nullable=False, default=0)
    payment_provider = db.Column(db.String(40), nullable=True)
    payment_status = db.Column(db.String(20), nullable=False, default="pending")
    payment_reference = db.Column(db.String(255), nullable=True)
    activated_at = db.Column(db.DateTime, nullable=True)
    upgrade_prompt_shown_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "plan": self.plan,
            "status": self.status,
            "renewed_on": self.renewed_on.isoformat(),
            "trial_start_date": self.trial_start_date.isoformat() if self.trial_start_date else None,
            "trial_end_date": self.trial_end_date.isoformat() if self.trial_end_date else None,
            "promo_code_used": self.promo_code_used or "",
            "promo_discount_percent": self.promo_discount_percent or 0,
            "promo_discount_amount": self.promo_discount_amount or 0,
            "amount_due": self.amount_due or 0,
            "payment_provider": self.payment_provider or "",
            "payment_status": self.payment_status or "pending",
            "payment_reference": self.payment_reference or "",
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "upgrade_prompt_shown_at": (
                self.upgrade_prompt_shown_at.isoformat() if self.upgrade_prompt_shown_at else None
            ),
        }


class Setting(TimestampMixin, db.Model):
    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    key = db.Column(db.String(120), nullable=False)
    value = db.Column(db.Text, nullable=True)

    __table_args__ = (
        db.UniqueConstraint("user_id", "key", name="uniq_user_setting_key"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "key": self.key,
            "value": self.value or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ApiKey(TimestampMixin, db.Model):
    __tablename__ = "api_keys"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    service_name = db.Column(db.String(80), nullable=False)
    encrypted_key = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="saved")

    __table_args__ = (
        db.UniqueConstraint("user_id", "service_name", name="uniq_user_service_key"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "service_name": self.service_name,
            "has_key": bool(self.encrypted_key),
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class WhatsAppSetting(TimestampMixin, db.Model):
    __tablename__ = "whatsapp_settings"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    api_key_encrypted = db.Column(db.Text, nullable=True)
    phone_number_id = db.Column(db.String(120), nullable=True)
    business_account_id = db.Column(db.String(120), nullable=True)
    verify_token_encrypted = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="disconnected")
    last_error = db.Column(db.Text, nullable=True)
    last_verified_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "phone_number_id": self.phone_number_id or "",
            "business_account_id": self.business_account_id or "",
            "status": self.status,
            "last_error": self.last_error or "",
            "last_verified_at": self.last_verified_at.isoformat() if self.last_verified_at else None,
        }


class WhatsAppMessage(TimestampMixin, db.Model):
    __tablename__ = "whatsapp_messages"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True, index=True)
    recipient_phone = db.Column(db.String(25), nullable=False)
    message = db.Column(db.Text, nullable=False)
    template_name = db.Column(db.String(120), nullable=True)
    message_type = db.Column(db.String(40), nullable=False, default="text")
    mode = db.Column(db.String(20), nullable=False, default="demo")
    status = db.Column(db.String(20), nullable=False, default="queued")
    external_message_id = db.Column(db.String(255), nullable=True)
    scheduled_for = db.Column(db.DateTime, nullable=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "customer_id": self.customer_id,
            "customer_name": self.customer.name if self.customer else None,
            "recipient_phone": self.recipient_phone,
            "message": self.message,
            "template_name": self.template_name or "",
            "message_type": self.message_type,
            "mode": self.mode,
            "status": self.status,
            "external_message_id": self.external_message_id or "",
            "scheduled_for": self.scheduled_for.isoformat() if self.scheduled_for else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "error_message": self.error_message or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class WhatsAppTemplate(TimestampMixin, db.Model):
    __tablename__ = "whatsapp_templates"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    template_name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(60), nullable=False, default="custom")
    content = db.Column(db.Text, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "template_name": self.template_name,
            "category": self.category,
            "content": self.content,
            "is_builtin": False,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
