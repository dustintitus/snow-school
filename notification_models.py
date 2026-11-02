"""Durable inbox and push outbox. The current database represents one school."""
from models import db

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    school = db.Column(db.String(40), nullable=False, default='HORSESHOE', index=True)
    category = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    event_key = db.Column(db.String(200), unique=True)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())

class NotificationRecipient(db.Model):
    __table_args__ = (db.UniqueConstraint('notification_id', 'user_id'),)
    id = db.Column(db.Integer, primary_key=True)
    notification_id = db.Column(db.Integer, db.ForeignKey('notification.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    read_at = db.Column(db.DateTime)
    notification = db.relationship('Notification')

class NotificationPreference(db.Model):
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    push_enabled = db.Column(db.Boolean, nullable=False, default=False)
    school_enabled = db.Column(db.Boolean, nullable=False, default=True)
    schedule_enabled = db.Column(db.Boolean, nullable=False, default=True)
    evaluation_enabled = db.Column(db.Boolean, nullable=False, default=True)

class PushDevice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(200), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    session_key = db.Column(db.String(100), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())

class PushDelivery(db.Model):
    __table_args__ = (db.UniqueConstraint('recipient_id', 'device_id'),)
    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('notification_recipient.id'), nullable=False)
    device_id = db.Column(db.Integer, db.ForeignKey('push_device.id'), nullable=False)
    status = db.Column(db.String(30), nullable=False, default='pending')
    attempts = db.Column(db.Integer, nullable=False, default=0)
    ticket_id = db.Column(db.String(100))
    error = db.Column(db.String(80))
    retry_at = db.Column(db.DateTime)
    recipient = db.relationship('NotificationRecipient')
    device = db.relationship('PushDevice')

class NotificationWorkerLease(db.Model):
    name = db.Column(db.String(40), primary_key=True)
    holder = db.Column(db.String(40))
    until = db.Column(db.DateTime, nullable=False)

class NotificationDraft(db.Model):
    key = db.Column(db.String(40), primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    body = db.Column(db.Text, nullable=False)
    recipient_ids = db.Column(db.JSON, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
