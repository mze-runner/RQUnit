pub struct Money {
    pub amount: i64,
    pub currency: String,
}

pub struct OrderView {
    pub id: String,
    pub total: Money,
    #[serde(rename = "placed_at")]
    pub placed: String,
    #[serde(skip)]
    pub internal_cost: i64,
}

pub struct CancelRequest {
    pub reason: String,
}

pub async fn get_order(Path(id): Path<String>) -> Json<OrderView> {
    todo!()
}

pub async fn cancel_order(Json(body): Json<CancelRequest>) -> Json<OrderView> {
    todo!()
}

pub fn router() -> Router {
    Router::new()
        .route("/{id}", get(get_order))
        .route("/{id}/cancel", post(cancel_order))
}
