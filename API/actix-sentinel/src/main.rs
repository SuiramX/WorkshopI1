use actix_cors::Cors;
use actix_web::{App, HttpResponse, HttpServer, Responder, get, post, web};
use chrono;
use dotenvy::dotenv;
use std::{
    env, fs,
    io::Cursor,
    process::Command,
    time::Duration,
};

// DB Interactions
use sea_orm::{
    ColumnTrait, ConnectOptions, Database, DatabaseConnection, EntityTrait, QueryFilter,
    QueryOrder, entity::prelude::*,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

/* #region DB ENTITIES */

pub mod temperature {
    use super::*;

    #[derive(Clone, Debug, PartialEq, DeriveEntityModel, Serialize, Deserialize)]
    #[sea_orm(table_name = "temperatures")]
    pub struct Model {
        #[sea_orm(primary_key, auto_increment = false)]
        pub date: DateTimeUtc,
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
        pub date: DateTimeUtc,
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
        pub date: DateTimeUtc,
        pub gas_level: f64,
    }

    #[derive(Copy, Clone, Debug, EnumIter, DeriveRelation)]
    pub enum Relation {}

    impl ActiveModelBehavior for ActiveModel {}
}

/* #endregion */

/* #region INTERFACE STRUCT */

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
struct TemperaturePayload {
    pub date: Option<DateTimeUtc>,
    pub temperature: f64,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
struct HumidityPayload {
    pub date: Option<DateTimeUtc>,
    pub humidity: f64,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
struct GasPayload {
    pub date: Option<DateTimeUtc>,
    pub gas_level: f64,
}

#[derive(Deserialize)]
struct DateRange {
    start_date: Option<String>,
    end_date: Option<String>,
}

fn parse_date_boundary(s: &str, is_end: bool) -> Option<DateTimeUtc> {
    // 1. Essai de parsing RFC3339 / ISO 8601 complet (ex: 2026-10-08T12:00:00Z)
    if let Ok(dt) = chrono::DateTime::parse_from_rfc3339(s) {
        return Some(dt.with_timezone(&chrono::Utc));
    }
    // 2. Essai de parsing Date simple (ex: 2026-10-08)
    if let Ok(d) = chrono::NaiveDate::parse_from_str(s, "%Y-%m-%d") {
        if is_end {
            let dt = d.and_hms_opt(23, 59, 59)?.and_utc();
            return Some(dt);
        } else {
            let dt = d.and_hms_opt(0, 0, 0)?.and_utc();
            return Some(dt);
        }
    }
    // 3. Essai de parsing DateTime standard (ex: 2026-10-08 12:00:00)
    if let Ok(dt) = chrono::NaiveDateTime::parse_from_str(s, "%Y-%m-%d %H:%M:%S") {
        return Some(dt.and_utc());
    }
    None
}

/* #endregion */

struct AppState {
    app_name: String,
    conn: Option<DatabaseConnection>,
}

async fn db_connection() -> Option<DatabaseConnection> {
    let db_url = env::var("DATABASE_URL").unwrap_or_else(|_| "DB URL NOT SET".to_string());

    let mut opt = ConnectOptions::new(db_url);

    // Configure connection behavior
    opt.max_connections(10)
        .min_connections(1)
        .connect_timeout(Duration::from_secs(8))
        .acquire_timeout(Duration::from_secs(8))
        .idle_timeout(Duration::from_secs(8));

    let conn = Database::connect(opt).await;

    conn.ok()
}

fn tls_config() -> rustls::ServerConfig {
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
            fs::read(&cert_path).unwrap_or_else(|err| {
                panic!("Failed to read certificate at '{}': {}", cert_path, err)
            }),
            fs::read(&key_path).unwrap_or_else(|err| {
                panic!("Failed to read private key at '{}': {}", key_path, err)
            }),
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
    let tls_config: rustls::ServerConfig = rustls::ServerConfig::builder()
        .with_no_client_auth()
        .with_single_cert(tls_certs, rustls::pki_types::PrivateKeyDer::Pkcs8(tls_key))
        .unwrap();

    tls_config
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    dotenv().ok();
    let host = env::var("HOST").unwrap_or_else(|_| "0.0.0.0".to_string());
    let port = env::var("PORT").unwrap_or_else(|_| "8080".to_string());

    // DB Connection
    let conn = db_connection().await;

    // App State
    let state = web::Data::new(AppState {
        app_name: String::from("Sentinel API"),
        conn,
    });

    // TLS / HTTPS
    let tls_config = tls_config();

    // Start Server
    HttpServer::new(move || {
        let cors = Cors::permissive();

        App::new()
            .wrap(cors)
            .app_data(state.clone())
            .service(actix_sentinel)
            .service(get_date)
            // Temperatures
            .service(sensor_temperature)
            .service(create_temperature)
            .service(read_temperature)
            .service(read_temperature_range)
            // Humidity
            .service(sensor_humidity)
            .service(create_humidity)
            .service(read_humidity)
            .service(read_humidity_range)
            // Gas
            .service(sensor_gas)
            .service(create_gas)
            .service(read_gas)
            .service(read_gas_range)
            // Presence
            .service(sensor_presence)
            // All
            .service(get_status)
            .service(post_status)
            .service(get_all_sensors)
    })
    .keep_alive(Duration::from_secs(75))
    .bind_rustls_0_23((host.as_str(), port.parse().unwrap()), tls_config)?
    .run()
    .await
}

/* #region MAIN ROUTES */

#[get("/")]
async fn actix_sentinel(state: web::Data<AppState>) -> impl Responder {
    let app_name = &state.app_name;
    HttpResponse::Ok().body(format!("{}", app_name))
}

#[get("/date")]
async fn get_date(_state: web::Data<AppState>) -> impl Responder {
    let current_timestamp = chrono::Utc::now().to_rfc3339();
    HttpResponse::Ok().body(format!("current date : {}", current_timestamp))
}

/* #endregion */

/* #region TEMPERATURE */

async fn get_latest_temp(conn: &DatabaseConnection) -> Option<temperature::Model> {
    let latest_temp = temperature::Entity::find()
        .order_by_desc(temperature::Column::Date)
        .one(conn)
        .await;

    match latest_temp {
        Ok(Some(entry)) => Some(entry),
        Ok(None) | Err(_) => None,
    }
}

fn get_mqtt_host() -> String {
    env::var("MQTT_HOST").unwrap_or_else(|_| "192.168.1.9".to_string())
}

/// Get Temperature from Sensor and Store to DB with precise Timestamp
#[get("/temperature/sensor")]
async fn sensor_temperature(state: web::Data<AppState>) -> impl Responder {
    let mqtt_host = get_mqtt_host();
    let output = Command::new("mosquitto_pub")
        .arg("-h")
        .arg(&mqtt_host)
        .arg("-t")
        .arg("esp8266/cmd")
        .arg("-m")
        .arg("temp")
        .output();

    match output {
        Ok(out) => {
            if out.status.success() {
                // Get sensor value
                let stdout = String::from_utf8_lossy(&out.stdout).trim().to_string();
                let temp: Option<f64> = stdout.parse().ok();

                // Store entry to DB if connected
                if let Some(conn) = &state.conn && let Some(value) = temp {
                    let now = chrono::Utc::now();
                    let new_entry = temperature::ActiveModel {
                        date: sea_orm::Set(now),
                        temperature: sea_orm::Set(value),
                    };

                    if let Err(err) = new_entry.insert(conn).await {
                        eprintln!("Error inserting temperature: {err}");
                    }
                }

                HttpResponse::Ok().body(stdout)
            } else {
                let stderr = String::from_utf8_lossy(&out.stderr).to_string();
                HttpResponse::InternalServerError().body(stderr)
            }
        }
        Err(err) => HttpResponse::InternalServerError().body(err.to_string()),
    }
}

/// Take a temperature JSON and Store to DB
#[post("/temperature")]
async fn create_temperature(
    state: web::Data<AppState>,
    payload: web::Json<TemperaturePayload>,
) -> impl Responder {
    let Some(conn) = &state.conn else {
        return HttpResponse::InternalServerError().body("No DB Connection");
    };

    let date = payload.date.unwrap_or_else(|| chrono::Utc::now());

    let new_entry = temperature::ActiveModel {
        date: sea_orm::Set(date),
        temperature: sea_orm::Set(payload.temperature),
    };

    match new_entry.insert(conn).await {
        Ok(inserted) => HttpResponse::Created().json(json!({
            "date": inserted.date.to_rfc3339(),
            "temperature": inserted.temperature,
        })),
        Err(err) => HttpResponse::InternalServerError().body(err.to_string()),
    }
}

/// Get Latest Temperature
#[get("/temperature")]
async fn read_temperature(state: web::Data<AppState>) -> impl Responder {
    let Some(conn) = &state.conn else {
        return HttpResponse::InternalServerError().body("No DB Connection");
    };

    let temperature = get_latest_temp(conn).await;

    if let Some(temperature) = temperature {
        let temp = json!({
            "date": temperature.date.to_rfc3339(),
            "temperature": temperature.temperature,
        });

        return HttpResponse::Ok().json(temp);
    }

    HttpResponse::NotFound().body("No DB entry")
}

/// Get all Temperatures in the Date Range
#[get("/temperature/range")]
async fn read_temperature_range(
    state: web::Data<AppState>,
    date_range: web::Query<DateRange>,
) -> impl Responder {
    let Some(conn) = &state.conn else {
        return HttpResponse::InternalServerError().body("No DB Connection");
    };

    let start_dt = date_range
        .start_date
        .as_deref()
        .and_then(|s| parse_date_boundary(s, false))
        .unwrap_or_else(|| chrono::Utc::now() - chrono::Duration::days(1));

    let end_dt = date_range
        .end_date
        .as_deref()
        .and_then(|s| parse_date_boundary(s, true))
        .unwrap_or_else(|| chrono::Utc::now());

    let temperatures = temperature::Entity::find()
        .filter(temperature::Column::Date.between(start_dt, end_dt))
        .order_by_asc(temperature::Column::Date)
        .all(conn)
        .await;

    match temperatures {
        Ok(records) => {
            let response: Vec<Value> = records
                .into_iter()
                .map(|record| {
                    json!({
                        "date": record.date.to_rfc3339(),
                        "temperature": record.temperature,
                    })
                })
                .collect();
            HttpResponse::Ok().json(response)
        }
        Err(err) => HttpResponse::InternalServerError().body(err.to_string()),
    }
}

/* #endregion */

/* #region HUMIDITY */

async fn get_latest_humidity(conn: &DatabaseConnection) -> Option<humidity::Model> {
    let latest_hum = humidity::Entity::find()
        .order_by_desc(humidity::Column::Date)
        .one(conn)
        .await;

    match latest_hum {
        Ok(Some(entry)) => Some(entry),
        Ok(None) | Err(_) => None,
    }
}

/// Get Humidity from Sensor and Store to DB with precise Timestamp
#[get("/humidity/sensor")]
async fn sensor_humidity(state: web::Data<AppState>) -> impl Responder {
    let mqtt_host = get_mqtt_host();
    let output = Command::new("mosquitto_pub")
        .arg("-h")
        .arg(&mqtt_host)
        .arg("-t")
        .arg("esp8266/cmd")
        .arg("-m")
        .arg("hum")
        .output();

    match output {
        Ok(out) => {
            if out.status.success() {
                // Get sensor value
                let stdout = String::from_utf8_lossy(&out.stdout).trim().to_string();
                let hum: Option<f64> = stdout.parse().ok();

                // Store entry to DB if connected
                if let Some(conn) = &state.conn && let Some(value) = hum {
                    let now = chrono::Utc::now();
                    let new_entry = humidity::ActiveModel {
                        date: sea_orm::Set(now),
                        humidity: sea_orm::Set(value),
                    };

                    if let Err(err) = new_entry.insert(conn).await {
                        eprintln!("Error inserting humidity: {err}");
                    }
                }

                HttpResponse::Ok().body(stdout)
            } else {
                let stderr = String::from_utf8_lossy(&out.stderr).to_string();
                HttpResponse::InternalServerError().body(stderr)
            }
        }
        Err(err) => HttpResponse::InternalServerError().body(err.to_string()),
    }
}

/// Take a humidity JSON and Store to DB
#[post("/humidity")]
async fn create_humidity(
    state: web::Data<AppState>,
    payload: web::Json<HumidityPayload>,
) -> impl Responder {
    let Some(conn) = &state.conn else {
        return HttpResponse::InternalServerError().body("No DB Connection");
    };

    let date = payload.date.unwrap_or_else(|| chrono::Utc::now());

    let new_entry = humidity::ActiveModel {
        date: sea_orm::Set(date),
        humidity: sea_orm::Set(payload.humidity),
    };

    match new_entry.insert(conn).await {
        Ok(inserted) => HttpResponse::Created().json(json!({
            "date": inserted.date.to_rfc3339(),
            "humidity": inserted.humidity,
        })),
        Err(err) => HttpResponse::InternalServerError().body(err.to_string()),
    }
}

/// Get Latest Humidity
#[get("/humidity")]
async fn read_humidity(state: web::Data<AppState>) -> impl Responder {
    let Some(conn) = &state.conn else {
        return HttpResponse::InternalServerError().body("No DB Connection");
    };

    let humidity = get_latest_humidity(conn).await;

    if let Some(humidity) = humidity {
        let hum = json!({
            "date": humidity.date.to_rfc3339(),
            "humidity": humidity.humidity,
        });

        return HttpResponse::Ok().json(hum);
    }

    HttpResponse::NotFound().body("No DB entry")
}

/// Get all Humidities in the Date Range
#[get("/humidity/range")]
async fn read_humidity_range(
    state: web::Data<AppState>,
    date_range: web::Query<DateRange>,
) -> impl Responder {
    let Some(conn) = &state.conn else {
        return HttpResponse::InternalServerError().body("No DB Connection");
    };

    let start_dt = date_range
        .start_date
        .as_deref()
        .and_then(|s| parse_date_boundary(s, false))
        .unwrap_or_else(|| chrono::Utc::now() - chrono::Duration::days(1));

    let end_dt = date_range
        .end_date
        .as_deref()
        .and_then(|s| parse_date_boundary(s, true))
        .unwrap_or_else(|| chrono::Utc::now());

    let humidities = humidity::Entity::find()
        .filter(humidity::Column::Date.between(start_dt, end_dt))
        .order_by_asc(humidity::Column::Date)
        .all(conn)
        .await;

    match humidities {
        Ok(records) => {
            let response: Vec<Value> = records
                .into_iter()
                .map(|record| {
                    json!({
                        "date": record.date.to_rfc3339(),
                        "humidity": record.humidity,
                    })
                })
                .collect();
            HttpResponse::Ok().json(response)
        }
        Err(err) => HttpResponse::InternalServerError().body(err.to_string()),
    }
}

/* #endregion */

/* #region GAS */

async fn get_latest_gas_level(conn: &DatabaseConnection) -> Option<gas::Model> {
    let latest_gas = gas::Entity::find()
        .order_by_desc(gas::Column::Date)
        .one(conn)
        .await;

    match latest_gas {
        Ok(Some(entry)) => Some(entry),
        Ok(None) | Err(_) => None,
    }
}

/// Get Gas from Sensor and Store to DB with precise Timestamp
#[get("/gas/sensor")]
async fn sensor_gas(state: web::Data<AppState>) -> impl Responder {
    let mqtt_host = get_mqtt_host();
    let output = Command::new("mosquitto_pub")
        .arg("-h")
        .arg(&mqtt_host)
        .arg("-t")
        .arg("esp8266/cmd")
        .arg("-m")
        .arg("gaz")
        .output();

    match output {
        Ok(out) => {
            if out.status.success() {
                // Get sensor value
                let stdout = String::from_utf8_lossy(&out.stdout).trim().to_string();
                let gas_val: Option<f64> = stdout.parse().ok();

                // Store entry to DB if connected
                if let Some(conn) = &state.conn && let Some(value) = gas_val {
                    let now = chrono::Utc::now();
                    let new_entry = gas::ActiveModel {
                        date: sea_orm::Set(now),
                        gas_level: sea_orm::Set(value),
                    };

                    if let Err(err) = new_entry.insert(conn).await {
                        eprintln!("Error inserting gas: {err}");
                    }
                }

                HttpResponse::Ok().body(stdout)
            } else {
                let stderr = String::from_utf8_lossy(&out.stderr).to_string();
                HttpResponse::InternalServerError().body(stderr)
            }
        }
        Err(err) => HttpResponse::InternalServerError().body(err.to_string()),
    }
}

/// Take a gas JSON and Store to DB
#[post("/gas")]
async fn create_gas(state: web::Data<AppState>, payload: web::Json<GasPayload>) -> impl Responder {
    let Some(conn) = &state.conn else {
        return HttpResponse::InternalServerError().body("No DB Connection");
    };

    let date = payload.date.unwrap_or_else(|| chrono::Utc::now());

    let new_entry = gas::ActiveModel {
        date: sea_orm::Set(date),
        gas_level: sea_orm::Set(payload.gas_level),
    };

    match new_entry.insert(conn).await {
        Ok(inserted) => HttpResponse::Created().json(json!({
            "date": inserted.date.to_rfc3339(),
            "gas_level": inserted.gas_level,
        })),
        Err(err) => HttpResponse::InternalServerError().body(err.to_string()),
    }
}

/// Get Latest Gas Level
#[get("/gas")]
async fn read_gas(state: web::Data<AppState>) -> impl Responder {
    let Some(conn) = &state.conn else {
        return HttpResponse::InternalServerError().body("No DB Connection");
    };

    let gas = get_latest_gas_level(conn).await;

    if let Some(gas) = gas {
        let gas_json = json!({
            "date": gas.date.to_rfc3339(),
            "gas": gas.gas_level,
            "gas_level": gas.gas_level,
        });

        return HttpResponse::Ok().json(gas_json);
    }

    HttpResponse::NotFound().body("No DB entry")
}

/// Get all Gases in the Date Range
#[get("/gas/range")]
async fn read_gas_range(
    state: web::Data<AppState>,
    date_range: web::Query<DateRange>,
) -> impl Responder {
    let Some(conn) = &state.conn else {
        return HttpResponse::InternalServerError().body("No DB Connection");
    };

    let start_dt = date_range
        .start_date
        .as_deref()
        .and_then(|s| parse_date_boundary(s, false))
        .unwrap_or_else(|| chrono::Utc::now() - chrono::Duration::days(1));

    let end_dt = date_range
        .end_date
        .as_deref()
        .and_then(|s| parse_date_boundary(s, true))
        .unwrap_or_else(|| chrono::Utc::now());

    let gases = gas::Entity::find()
        .filter(gas::Column::Date.between(start_dt, end_dt))
        .order_by_asc(gas::Column::Date)
        .all(conn)
        .await;

    match gases {
        Ok(records) => {
            let response: Vec<Value> = records
                .into_iter()
                .map(|record| {
                    json!({
                        "date": record.date.to_rfc3339(),
                        "gas_level": record.gas_level,
                    })
                })
                .collect();
            HttpResponse::Ok().json(response)
        }
        Err(err) => HttpResponse::InternalServerError().body(err.to_string()),
    }
}

/* #endregion */

/* #region PRESENCE */

/// Get Presence Sensor Value
#[get("/presence")]
async fn sensor_presence(_state: web::Data<AppState>) -> impl Responder {
    let mqtt_host = get_mqtt_host();
    let output = Command::new("mosquitto_pub")
        .arg("-h")
        .arg(&mqtt_host)
        .arg("-t")
        .arg("esp8266/cmd")
        .arg("-m")
        .arg("mouv")
        .output();

    match output {
        Ok(out) => {
            if out.status.success() {
                let stdout = String::from_utf8_lossy(&out.stdout).to_string();
                HttpResponse::Ok().body(stdout)
            } else {
                let stderr = String::from_utf8_lossy(&out.stderr).to_string();
                HttpResponse::InternalServerError().body(stderr)
            }
        }
        Err(err) => HttpResponse::InternalServerError().body(err.to_string()),
    }
}

/* #endregion */

/* #region ALL SENSORS */

/// Get all sensors value
#[get("/status/sensors")]
async fn get_all_sensors(_state: web::Data<AppState>) -> impl Responder {
    let mqtt_host = get_mqtt_host();
    let output = Command::new("mosquitto_pub")
        .arg("-h")
        .arg(&mqtt_host)
        .arg("-t")
        .arg("esp8266/cmd")
        .arg("-m")
        .arg("get_all")
        .output();

    match output {
        Ok(out) => {
            if out.status.success() {
                let stdout = String::from_utf8_lossy(&out.stdout).to_string();
                HttpResponse::Ok().body(stdout)
            } else {
                let stderr = String::from_utf8_lossy(&out.stderr).to_string();
                HttpResponse::InternalServerError().body(stderr)
            }
        }
        Err(err) => HttpResponse::InternalServerError().body(err.to_string()),
    }
}

fn trigger_sensors_poll() {
    let mqtt_host = get_mqtt_host();
    for cmd in &["get_all", "temp", "hum", "gaz"] {
        let _ = Command::new("mosquitto_pub")
            .arg("-h")
            .arg(&mqtt_host)
            .arg("-t")
            .arg("esp8266/cmd")
            .arg("-m")
            .arg(cmd)
            .output();
    }
}

async fn handle_status(state: web::Data<AppState>) -> impl Responder {
    let Some(conn) = &state.conn else {
        return HttpResponse::InternalServerError().body("No DB Connection");
    };

    // Déclenche la récupération des capteurs via MQTT de manière non-bloquante
    let _ = tokio::task::spawn_blocking(trigger_sensors_poll).await;

    let mut response: Vec<Value> = vec![];

    // temp
    let temperature = get_latest_temp(conn).await;
    if let Some(temperature) = temperature {
        response.push(json!({
            "date": temperature.date.to_rfc3339(),
            "temperature_level": temperature.temperature,
        }));
    }

    // humidity
    let humidity = get_latest_humidity(conn).await;
    if let Some(humidity) = humidity {
        response.push(json!({
            "date": humidity.date.to_rfc3339(),
            "humidity_level": humidity.humidity,
        }));
    }

    // gas
    let gas = get_latest_gas_level(conn).await;
    if let Some(gas) = gas {
        response.push(json!({
            "date": gas.date.to_rfc3339(),
            "gas_level": gas.gas_level,
        }));
    }

    HttpResponse::Ok().json(response)
}

/// Get Latest Sensors Values with precise Timestamps
#[get("/status")]
async fn get_status(state: web::Data<AppState>) -> impl Responder {
    handle_status(state).await
}

/// Trigger & Get Latest Sensors Values via POST
#[post("/status")]
async fn post_status(state: web::Data<AppState>) -> impl Responder {
    handle_status(state).await
}

/* #endregion */
