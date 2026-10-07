use actix_web::{App, HttpResponse, HttpServer, Responder, get, post, web};
use dotenvy::dotenv;
use std::{env, fs::File, io::BufReader, process::Command, time::Duration};

use sea_orm::{Database, DatabaseConnection, EntityTrait, QueryOrder, entity::prelude::*};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use chrono;

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

    // DB + App State
    let port = env::var("PORT").unwrap_or_else(|_| "8080".to_string());
    let db_url = env::var("DATABASE_URL").expect("DB URL");

    let conn: DatabaseConnection = Database::connect(db_url)
        .await
        .expect("Failed to connect to database");

    let state = web::Data::new(AppState {
        app_name: String::from("Sentinel API"),
        conn,
    });

    // TLS / HTTTPS
    rustls::crypto::aws_lc_rs::default_provider()
        .install_default()
        .unwrap();

    let mut certs_file = BufReader::new(File::open("cert.pem").unwrap());
    let mut key_file = BufReader::new(File::open("key.pem").unwrap());

    // load TLS certs and key
    let tls_certs = rustls_pemfile::certs(&mut certs_file)
        .collect::<Result<Vec<_>, _>>()
        .unwrap();
    let tls_key = rustls_pemfile::pkcs8_private_keys(&mut key_file)
        .next()
        .unwrap()
        .unwrap();

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
            .service(get_temperature_test)
            .service(add_temperature)
            .service(get_temperatures)
            .service(get_humidity_test)
            .service(add_humidity)
            .service(get_humidities)
            .service(get_gas_test)
            .service(add_gas)
            .service(get_gases)
            .service(get_status)
            .service(presence)
            .service(get_temperature_test)
    })
    .keep_alive(Duration::from_secs(75))
    // .bind_rustls_0_23(("127.0.0.1", port.parse().unwrap()), tls_config)?
    .bind_rustls_0_23(("0.0.0.0", port.parse().unwrap()), tls_config)? // 0.0.0.0 = docker bind
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

/// Get temp from Sensors + store in DB
#[get("/temperature_sensor")]
async fn get_temperature_test(state: web::Data<AppState>) -> impl Responder {
    // mosquitto_pub -h 192.168.1.9 -t "esp8266/cmd" -m "temp"
    let output = Command::new("mosquitto_pub")
        .arg("-h")
        .arg("192.168.1.9")
        .arg("-t")
        .arg("'esp8266/cmd'")
        .arg("-m")
        .arg("'temp'")
        .output();

    return match output {
        Ok(out) => {
            if out.status.success() {
                let stdout = String::from_utf8_lossy(&out.stdout).to_string();

                let new_entry = temperature::ActiveModel {
                    date: sea_orm::Set(chrono::naive::NaiveDate::from_ymd_opt(2026, 10, 07).unwrap()),
                    temperature: sea_orm::Set(stdout.parse().unwrap()),
                };

                HttpResponse::Ok().body(stdout)
            } else {
                let stderr = String::from_utf8_lossy(&out.stderr).to_string();
                HttpResponse::InternalServerError().body(stderr)
            }
        }
        Err(err) => HttpResponse::InternalServerError().body(err.to_string()),
    };
}

/// Add temperature to DB -> from JSON in http Request
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
#[get("/temperatures")]
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

/// Get hum from Sensors + store in DB
#[get("/humidity_sensor")]
async fn get_humidity_test(state: web::Data<AppState>) -> impl Responder {
    // mosquitto_pub -h 192.168.1.9 -t "esp8266/cmd" -m "hum"
    let output = Command::new("mosquitto_pub")
        .arg("-h")
        .arg("192.168.1.9")
        .arg("-t")
        .arg("'esp8266/cmd'")
        .arg("-m")
        .arg("'hum'")
        .output();

    return match output {
        Ok(out) => {
            if out.status.success() {
                let stdout = String::from_utf8_lossy(&out.stdout).to_string();

                let new_entry = humidity::ActiveModel {
                    date: sea_orm::Set(chrono::naive::NaiveDate::from_ymd_opt(2026, 10, 07).unwrap()),
                    humidity: sea_orm::Set(stdout.parse().unwrap()),
                };

                HttpResponse::Ok().body(stdout)
            } else {
                let stderr = String::from_utf8_lossy(&out.stderr).to_string();
                HttpResponse::InternalServerError().body(stderr)
            }
        }
        Err(err) => HttpResponse::InternalServerError().body(err.to_string()),
    };
}

#[post("/humidity")]
async fn add_humidity(state: web::Data<AppState>, payload: web::Json<Humidity>) -> impl Responder {
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

/// Get gas from Sensors + store in DB
#[get("/gas_sensor")]
async fn get_gas_test(state: web::Data<AppState>) -> impl Responder {
    // mosquitto_pub -h 192.168.1.9 -t "esp8266/cmd" -m "hum"
    let output = Command::new("mosquitto_pub")
        .arg("-h")
        .arg("192.168.1.9")
        .arg("-t")
        .arg("'esp8266/cmd'")
        .arg("-m")
        .arg("'gaz'")
        .output();

    return match output {
        Ok(out) => {
            if out.status.success() {
                let stdout = String::from_utf8_lossy(&out.stdout).to_string();

                let new_entry = gas::ActiveModel {
                    date: sea_orm::Set(chrono::naive::NaiveDate::from_ymd_opt(2026, 10, 07).unwrap()),
                    gas_level: sea_orm::Set(stdout.parse().unwrap()),
                };

                HttpResponse::Ok().body(stdout)
            } else {
                let stderr = String::from_utf8_lossy(&out.stderr).to_string();
                HttpResponse::InternalServerError().body(stderr)
            }
        }
        Err(err) => HttpResponse::InternalServerError().body(err.to_string()),
    };
}

#[post("/gas")]
async fn add_gas(state: web::Data<AppState>, payload: web::Json<Gas>) -> impl Responder {
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

/// Get all sensor
#[get("/all_sensors")]
async fn get_all_sensors(state: web::Data<AppState>) -> impl Responder {
    // mosquitto_pub -h 192.168.1.9 -t "esp8266/cmd" -m "get_all"
    let output = Command::new("mosquitto_pub")
        .arg("-h")
        .arg("192.168.1.9")
        .arg("-t")
        .arg("'esp8266/cmd'")
        .arg("-m")
        .arg("'get_all'")
        .output();

    return match output {
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
    };
}

/// Get Latest Sensors Values
#[get("/status")]
async fn get_status(state: web::Data<AppState>) -> impl Responder {
    let mut response: Vec<Value> = vec![];

    // temp
    let latest_temp = temperature::Entity::find()
        .order_by_desc(temperature::Column::Date)
        .one(&state.conn)
        .await;

    let temperature: Option<temperature::Model> = match latest_temp {
        Ok(Some(entry)) => Some(entry),
        Ok(None) => None,
        Err(err) => None,
    };

    if let Some(temperature) = temperature {
        response.push(json!({
            "date": temperature.date.to_string(),
            "temperature_level": &temperature.temperature,
        }));
    }

    // humidity
    let latest_humidity = humidity::Entity::find()
        .order_by_desc(humidity::Column::Date)
        .one(&state.conn)
        .await;

    let humidity: Option<humidity::Model> = match latest_humidity {
        Ok(Some(entry)) => Some(entry),
        Ok(None) => None,
        Err(err) => None,
    };

    if let Some(humidity) = humidity {
        response.push(json!({
            "date": humidity.date.to_string(),
            "humidity_level": &humidity.humidity,
        }));
    }

    // gas
    let latest_gas = gas::Entity::find()
        .order_by_desc(gas::Column::Date)
        .one(&state.conn)
        .await;

    let gas: Option<gas::Model> = match latest_gas {
        Ok(Some(entry)) => Some(entry),
        Ok(None) => None,
        Err(err) => None,
    };

    if let Some(gas) = gas {
        response.push(json!({
            "date": gas.date.to_string(),
            "gas_level": gas.gas_level,
        }));
    }

    return HttpResponse::Ok().json(response);
}

#[get("/presence")]
async fn presence(state: web::Data<AppState>) -> impl Responder {
    println!("Presence Detected");
    // TODO

    HttpResponse::Ok().body(format!("Presence Detected"))
}

/// Get Mouvement
#[get("/mouv")]
async fn get_all_sensors(state: web::Data<AppState>) -> impl Responder {
    // mosquitto_pub -h 192.168.1.9 -t "esp8266/cmd" -m "get_all"
    let output = Command::new("mosquitto_pub")
        .arg("-h")
        .arg("192.168.1.9")
        .arg("-t")
        .arg("'esp8266/cmd'")
        .arg("-m")
        .arg("'mouv'")
        .output();

    return match output {
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
    };
}

/* #endregion */
