pub async fn publish_lifecycle_events(bus: &Bus) {
    bus.publish(ORDER_PLACED, b"...").await;
    bus.publish(ORDER_CANCELLED, b"...").await;
}
