pub async fn cancel(order_id: &str, audit: &AuditSink) {
    audit.record(AUDIT_ORDER_CANCELLED, order_id).await;
}
