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

/// Erased: `Response` is what a handler returns after `.into_response()`, so
/// the truthful observation is that this handler's return type carries no
/// shape. The expectation records an endpoint with NO `outbound` at all —
/// omission means "not observed", and reporting the wrapper as a type name
/// would make every erased handler look like it served one shared shape.
pub async fn place_order(Json(body): Json<CancelRequest>) -> Response {
    todo!()
}

/// Erased through a fallible wrapper. The payload of a wrapper is its first
/// type argument or nothing — never the error type.
pub async fn amend_order(Path(id): Path<String>) -> Result<impl IntoResponse, AppError> {
    todo!()
}

pub fn router() -> Router {
    Router::new()
        .route("/{id}", get(get_order))
        .route("/{id}/cancel", post(cancel_order))
        .route("/bulk", post(place_order))
        .route("/{id}/amend", patch(amend_order))
}
