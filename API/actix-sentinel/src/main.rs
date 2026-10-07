use std::{env, fs, io::{BufReader, Cursor}, time::Duration};
use actix_web::{App, HttpResponse, HttpServer, Responder, get, post, web};
use dotenvy::dotenv;

use sea_orm::{entity::prelude::*, Database, DatabaseConnection, EntityTrait};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

/* #region DB ENTITIES */

pub mod temperature {
    use super::*;

    #[derive(Clone, Debug, PartialEq, DeriveEntityModel, Serialize, Deserialize)]
    #[sea_orm(table_name = "temperatures")]
    pub struct Model {
        #[sea_orm(primary_key, auto_increment = false)]
        pub date: Date,
        pub temperature: f64,
    }

    #[derive(Copy, Clone, Debug, EnumIter, DeriveRelation)]
    pub enum Relation {}

    impl ActiveModelBehavior for ActiveModel {}
}

pub mod humidity {
    use super::*;

    #[derive(Clone, Debug, PartialEq, DeriveEntityModel, Serialize, Deserialize)]
    #[sea_orm(table_name = "humidities")]
    pub struct Model {
        #[sea_orm(primary_key, auto_increment = false)]
        pub date: Date,
        pub humidity: f64,
    }

    #[derive(Copy, Clone, Debug, EnumIter, DeriveRelation)]
    pub enum Relation {}

    impl ActiveModelBehavior for ActiveModel {}
}

pub mod gas {
    use super::*;

    #[derive(Clone, Debug, PartialEq, DeriveEntityModel, Serialize, Deserialize)]
    #[sea_orm(table_name = "gases")]
    pub struct Model {
        #[sea_orm(primary_key, auto_increment = false)]
        pub date: Date,
        pub gas_level: f64,
    }

    #[derive(Copy, Clone, Debug, EnumIter, DeriveRelation)]
    pub enum Relation {}

    impl ActiveModelBehavior for ActiveModel {}
}

/* #endregion */

/* #region INTERFACE STRUCT */

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
struct Temperature {
    date: Date,
    temperature: f64,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
struct Humidity {
    date: Date,
    humidity: f64,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
struct Gas {
    date: Date,
    gas_level: f64,
}

#[derive(Deserialize)]
struct DateRange {
    start_date: Date,
    end_date: Date,
}

/* #endregion */

struct AppState {
    app_name: String,
    conn: DatabaseConnection,
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    dotenv().ok();
    
    let host = env::var("HOST").unwrap_or_else(|_| "0.0.0.0".to_string());
    let port = env::var("PORT").unwrap_or_else(|_| "8080".to_string());
    let db_url = env::var("DATABASE_URL").unwrap_or_else(|_| "Not configured".to_string());

    let conn: DatabaseConnection = Database::connect(db_url)
        .await
        .expect("Failed to connect to database");

    let state = web::Data::new(AppState {
        app_name: String::from("Sentinel API"),
        conn,
    });

    // TLS / HTTPS
    rustls::crypto::aws_lc_rs::default_provider()
        .install_default()
        .unwrap();

    // Load PEM certificate and private key directly from env (TLS_CERT / TLS_KEY) or fallback to file paths
    let (cert_bytes, key_bytes) = if let (Ok(cert_pem), Ok(key_pem)) = (
        env::var("TLS_CERT").or_else(|_| env::var("TLS_CERT_PEM")),
        env::var("TLS_KEY").or_else(|_| env::var("TLS_KEY_PEM")),
    ) {
        (
            cert_pem.replace("\\n", "\n").into_bytes(),
            key_pem.replace("\\n", "\n").into_bytes(),
        )
    } else {
        let cert_path = env::var("TLS_CERT_PATH").unwrap_or_else(|_| "cert.pem".to_string());
        let key_path = env::var("TLS_KEY_PATH").unwrap_or_else(|_| "key.pem".to_string());
        (
            fs::read(&cert_path)
                .unwrap_or_else(|err| panic!("Failed to read certificate at '{}': {}", cert_path, err)),
            fs::read(&key_path)
                .unwrap_or_else(|err| panic!("Failed to read private key at '{}': {}", key_path, err)),
        )
    };

    let mut certs_reader = Cursor::new(cert_bytes);
    let mut key_reader = Cursor::new(key_bytes);

    // load TLS certs and key
    let tls_certs = rustls_pemfile::certs(&mut certs_reader)
        .collect::<Result<Vec<_>, _>>()
        .expect("Failed to parse TLS certificate from PEM");
    let tls_key = rustls_pemfile::pkcs8_private_keys(&mut key_reader)
        .next()
        .expect("No PKCS8 private key found in PEM")
        .expect("Failed to parse PKCS8 private key");

    // set up TLS config options
    let tls_config = rustls::ServerConfig::builder()
        .with_no_client_auth()
        .with_single_cert(tls_certs, rustls::pki_types::PrivateKeyDer::Pkcs8(tls_key))
        .unwrap();

    // Start Server
    HttpServer::new(move || {
        App::new()
            .app_data(state.clone())
            .service(hello)
            .service(add_temperature)
            .service(get_temperatures)
            .service(add_humidity)
            .service(get_humidities)
            .service(add_gas)
            .service(get_gases)
    })
    .keep_alive(Duration::from_secs(75))
    .bind_rustls_0_23((host.as_str(), port.parse().unwrap()), tls_config)?
    .run()
    .await
}

/* #region ROUTES */

#[get("/")]
async fn hello(data: web::Data<AppState>) -> impl Responder {
    let app_name = &data.app_name;
    HttpResponse::Ok().body(format!("{}", app_name))
}

// Temperature

#[post("/temperature")]
async fn add_temperature(
    state: web::Data<AppState>,
    payload: web::Json<Temperature>,
) -> impl Responder {
    let new_entry = temperature::ActiveModel {
        date: sea_orm::Set(payload.date),
        temperature: sea_orm::Set(payload.temperature),
    };

    match new_entry.insert(&state.conn).await {
        Ok(inserted) => HttpResponse::Created().json(inserted),
        Err(err) => HttpResponse::InternalServerError().body(err.to_string()),
    }
}

/// Get all Temperatures in the Date Range
#[get("/temperature")]
async fn get_temperatures(
    state: web::Data<AppState>,
    date_range: web::Query<DateRange>,
) -> impl Responder {
    let start_date = date_range.start_date;
    let end_date = date_range.end_date;

    // Query between date range
    let temperatures = temperature::Entity::find()
        .filter(temperature::Column::Date.between(start_date, end_date))
        .all(&state.conn)
        .await
        .expect("Failed to fetch temperature data");

    let response: Vec<Value> = temperatures
    .into_iter()
    .map(|record| {
        json!({
            "date": record.date.to_string(),
            "temperature": record.temperature,
        })
    })
    .collect();

    HttpResponse::Ok().json(response)
}

// Humidity

#[post("/humidity")]
async fn add_humidity(
    state: web::Data<AppState>,
    payload: web::Json<Humidity>,
) -> impl Responder {
    let new_entry = humidity::ActiveModel {
        date: sea_orm::Set(payload.date),
        humidity: sea_orm::Set(payload.humidity),
    };

    match new_entry.insert(&state.conn).await {
        Ok(inserted) => HttpResponse::Created().json(inserted),
        Err(err) => HttpResponse::InternalServerError().body(err.to_string()),
    }
}

/// Get all Humidities in the Date Range
#[get("/humidity")]
async fn get_humidities(
    state: web::Data<AppState>,
    date_range: web::Query<DateRange>,
) -> impl Responder {
    let start_date = date_range.start_date;
    let end_date = date_range.end_date;

    // Query between date range
    let humidities = humidity::Entity::find()
        .filter(humidity::Column::Date.between(start_date, end_date))
        .all(&state.conn)
        .await
        .expect("Failed to fetch humidity data");

    let response: Vec<Value> = humidities
    .into_iter()
    .map(|record| {
        json!({
            "date": record.date.to_string(),
            "humidity": record.humidity,
        })
    })
    .collect();

    HttpResponse::Ok().json(response)
}

// Gas

#[post("/gas")]
async fn add_gas(
    state: web::Data<AppState>,
    payload: web::Json<Gas>,
) -> impl Responder {
    let new_entry = gas::ActiveModel {
        date: sea_orm::Set(payload.date),
        gas_level: sea_orm::Set(payload.gas_level),
    };

    match new_entry.insert(&state.conn).await {
        Ok(inserted) => HttpResponse::Created().json(inserted),
        Err(err) => HttpResponse::InternalServerError().body(err.to_string()),
    }
}

/// Get all Gases in the Date Range
#[get("/gas")]
async fn get_gases(
    state: web::Data<AppState>,
    date_range: web::Query<DateRange>,
) -> impl Responder {
    let start_date = date_range.start_date;
    let end_date = date_range.end_date;

    // Query between date range
    let gases = gas::Entity::find()
        .filter(gas::Column::Date.between(start_date, end_date))
        .all(&state.conn)
        .await
        .expect("Failed to fetch gas data");

    let response: Vec<Value> = gases
    .into_iter()
    .map(|record| {
        json!({
            "date": record.date.to_string(),
            "gas_level": record.gas_level,
        })
    })
    .collect();

    HttpResponse::Ok().json(response)
}

// TODO : STATUS & PRESENCE Routes

/* #endregion */