use actix_web::{App, HttpResponse, HttpServer, Responder, get, post, web};
use chrono;
use dotenvy::dotenv;
use std::{env, fs::File, io::BufReader, process::Command, time::Duration};

// DB Interactions
use sea_orm::{
    ConnectOptions, Database, DatabaseConnection, EntityTrait, QueryOrder, entity::prelude::*,
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

    // Panic on connection fail
    // let conn = Database::connect(opt).await.unwrap_or_else(|err| {
    //     eprintln!("Warning: Initial connection failed: {err}");
    //     panic!("Could not connect to database");
    // });

    let conn = Database::connect(opt).await;

    return conn.ok();
}

fn tls_config() -> rustls::ServerConfig {
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
    let tls_config: rustls::ServerConfig = rustls::ServerConfig::builder()
        .with_no_client_auth()
        .with_single_cert(tls_certs, rustls::pki_types::PrivateKeyDer::Pkcs8(tls_key))
        .unwrap();

    return tls_config;
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    dotenv().ok();
    let port = env::var("PORT").unwrap_or_else(|_| "8080".to_string());

    // DB Connection
    let conn = db_connection().await;

    // App State
    let state = web::Data::new(AppState {
        app_name: String::from("Sentinel API"),
        conn,
    });

    // TLS / HTTTPS
    let tls_config = tls_config();

    // Start Server
    HttpServer::new(move || {
        App::new()
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
            .service(get_all_sensors)
    })
    .keep_alive(Duration::from_secs(75))
    .bind_rustls_0_23(("127.0.0.1", port.parse().unwrap()), tls_config)?
    // .bind_rustls_0_23(("0.0.0.0", port.parse().unwrap()), tls_config)? // 0.0.0.0 = docker bind
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
async fn get_date(state: web::Data<AppState>) -> impl Responder {
    let current_date = chrono::Utc::now().naive_utc().date();
    HttpResponse::Ok().body(format!("current date : {}", current_date.to_string()))
}

/* #endregion */

/* #region TEMPERATURE */

async fn get_latest_temp(conn: &DatabaseConnection) -> Option<temperature::Model> {
    let latest_temp = temperature::Entity::find()
        .order_by_desc(temperature::Column::Date)
        .one(conn)
        .await;

    let temperature: Option<temperature::Model> = match latest_temp {
        Ok(Some(entry)) => Some(entry),
        Ok(None) => None,
        Err(err) => None,
    };

    return temperature;
}

/// Get Temperature from Sensor
/// Store to DB
#[get("/temperature/sensor")]
async fn sensor_temperature(state: web::Data<AppState>) -> impl Responder {
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
                let stdout = String::from_utf8_lossy(&out.stdout).to_string(); // json string

                // Store entry to DB if connected
                if let Some(conn) = &state.conn {
                    let current_date = chrono::Utc::now().naive_utc().date();
                    let new_entry = temperature::ActiveModel {
                        date: sea_orm::Set(current_date),
                        temperature: sea_orm::Set(stdout.parse().unwrap()),
                    };

                    let db_result = new_entry.insert(conn).await;
                }

                HttpResponse::Ok().body(stdout)
            } else {
                let stderr = String::from_utf8_lossy(&out.stderr).to_string();
                HttpResponse::InternalServerError().body(stderr)
            }
        }
        Err(err) => HttpResponse::InternalServerError().body(err.to_string()),
    };
}

/// Take a temperature JSON
/// Store to DB
#[post("/temperature")]
async fn create_temperature(
    state: web::Data<AppState>,
    payload: web::Json<Temperature>,
) -> impl Responder {
    let Some(conn) = &state.conn else {
        return HttpResponse::InternalServerError().body(format!("No DB Connection"));
    };

    let new_entry = temperature::ActiveModel {
        date: sea_orm::Set(payload.date),
        temperature: sea_orm::Set(payload.temperature),
    };

    match new_entry.insert(conn).await {
        Ok(inserted) => HttpResponse::Created().json(inserted),
        Err(err) => HttpResponse::InternalServerError().body(err.to_string()),
    }
}

/// Get Latest Temperature
#[get("/temperature")]
async fn read_temperature(state: web::Data<AppState>) -> impl Responder {
    let Some(conn) = &state.conn else {
        return HttpResponse::InternalServerError().body(format!("No DB Connection"));
    };

    // Query between date range
    let temperature = get_latest_temp(conn).await;

    if let Some(temperature) = temperature {
        let temp = json!({
            "date": temperature.date.to_string(),
            "temperature": &temperature.temperature,
        });

        return HttpResponse::Ok().json(temp);
    }

    return HttpResponse::InternalServerError().body(format!("No DB entry"));
}

/// Get all Temperatures in the Date Range
#[get("/temperature/range")]
async fn read_temperature_range(
    state: web::Data<AppState>,
    date_range: web::Query<DateRange>,
) -> impl Responder {
    let Some(conn) = &state.conn else {
        return HttpResponse::InternalServerError().body(format!("No DB Connection"));
    };

    let start_date = date_range.start_date;
    let end_date = date_range.end_date;

    // Query between date range
    let temperatures = temperature::Entity::find()
        .filter(temperature::Column::Date.between(start_date, end_date))
        .all(conn)
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

/* #endregion */

/* #region HUMIDITY */

async fn get_latest_humidity(conn: &DatabaseConnection) -> Option<humidity::Model> {
    let latest_temp = humidity::Entity::find()
        .order_by_desc(humidity::Column::Date)
        .one(conn)
        .await;

    let humidity: Option<humidity::Model> = match latest_temp {
        Ok(Some(entry)) => Some(entry),
        Ok(None) => None,
        Err(err) => None,
    };

    return humidity;
}

/// Get Humidity from Sensor
/// Store in DB
#[get("/humidity/sensor")]
async fn sensor_humidity(state: web::Data<AppState>) -> impl Responder {
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

                // Store entry to DB if connected
                if let Some(conn) = &state.conn {
                    let current_date = chrono::Utc::now().naive_utc().date();
                    let new_entry = humidity::ActiveModel {
                        date: sea_orm::Set(current_date),
                        humidity: sea_orm::Set(stdout.parse().unwrap()),
                    };

                    let db_result = new_entry.insert(conn).await;
                }

                HttpResponse::Ok().body(stdout)
            } else {
                let stderr = String::from_utf8_lossy(&out.stderr).to_string();
                HttpResponse::InternalServerError().body(stderr)
            }
        }
        Err(err) => HttpResponse::InternalServerError().body(err.to_string()),
    };
}

/// Take a humidity JSON
/// Store to DB
#[post("/humidity")]
async fn create_humidity(
    state: web::Data<AppState>,
    payload: web::Json<Humidity>,
) -> impl Responder {
    let Some(conn) = &state.conn else {
        return HttpResponse::InternalServerError().body(format!("No DB Connection"));
    };

    let new_entry = humidity::ActiveModel {
        date: sea_orm::Set(payload.date),
        humidity: sea_orm::Set(payload.humidity),
    };

    match new_entry.insert(conn).await {
        Ok(inserted) => HttpResponse::Created().json(inserted),
        Err(err) => HttpResponse::InternalServerError().body(err.to_string()),
    }
}

/// Get Latest Temperature
#[get("/humidity")]
async fn read_humidity(state: web::Data<AppState>) -> impl Responder {
    let Some(conn) = &state.conn else {
        return HttpResponse::InternalServerError().body(format!("No DB Connection"));
    };

    // Query between date range
    let humidity = get_latest_humidity(conn).await;

    if let Some(humidity) = humidity {
        let temp = json!({
            "date": humidity.date.to_string(),
            "humidity": &humidity.humidity,
        });

        return HttpResponse::Ok().json(temp);
    }

    return HttpResponse::InternalServerError().body(format!("No DB entry"));
}

/// Get all Humidities in the Date Range
#[get("/humidity/range")]
async fn read_humidity_range(
    state: web::Data<AppState>,
    date_range: web::Query<DateRange>,
) -> impl Responder {
    let Some(conn) = &state.conn else {
        return HttpResponse::InternalServerError().body(format!("No DB Connection"));
    };

    let start_date = date_range.start_date;
    let end_date = date_range.end_date;

    // Query between date range
    let humidities = humidity::Entity::find()
        .filter(humidity::Column::Date.between(start_date, end_date))
        .all(conn)
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

/* #endregion */

/* #region GAS */

async fn get_latest_gas_level(conn: &DatabaseConnection) -> Option<gas::Model> {
    let latest_temp = gas::Entity::find()
        .order_by_desc(gas::Column::Date)
        .one(conn)
        .await;

    let gas: Option<gas::Model> = match latest_temp {
        Ok(Some(entry)) => Some(entry),
        Ok(None) => None,
        Err(err) => None,
    };

    return gas;
}

/// Get Gaz from Sensor
/// Store in DB
#[get("/gas/sensor")]
async fn sensor_gas(state: web::Data<AppState>) -> impl Responder {
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

                // Store entry to DB if connected
                if let Some(conn) = &state.conn {
                    let current_date = chrono::Utc::now().naive_utc().date();
                    let new_entry = gas::ActiveModel {
                        date: sea_orm::Set(current_date),
                        gas_level: sea_orm::Set(stdout.parse().unwrap()),
                    };
                }

                HttpResponse::Ok().body(stdout)
            } else {
                let stderr = String::from_utf8_lossy(&out.stderr).to_string();
                HttpResponse::InternalServerError().body(stderr)
            }
        }
        Err(err) => HttpResponse::InternalServerError().body(err.to_string()),
    };
}

/// Take a gas JSON
/// Store entry to DB
#[post("/gas")]
async fn create_gas(state: web::Data<AppState>, payload: web::Json<Gas>) -> impl Responder {
    let Some(conn) = &state.conn else {
        return HttpResponse::InternalServerError().body(format!("No DB Connection"));
    };

    let new_entry = gas::ActiveModel {
        date: sea_orm::Set(payload.date),
        gas_level: sea_orm::Set(payload.gas_level),
    };

    match new_entry.insert(conn).await {
        Ok(inserted) => HttpResponse::Created().json(inserted),
        Err(err) => HttpResponse::InternalServerError().body(err.to_string()),
    }
}

/// Get Latest Gas Level
#[get("/gas")]
async fn read_gas(state: web::Data<AppState>) -> impl Responder {
    let Some(conn) = &state.conn else {
        return HttpResponse::InternalServerError().body(format!("No DB Connection"));
    };

    // Query between date range
    let gas = get_latest_gas_level(conn).await;

    if let Some(gas) = gas {
        let temp = json!({
            "date": gas.date.to_string(),
            "gas": &&gas.gas_level,
        });

        return HttpResponse::Ok().json(temp);
    }

    return HttpResponse::InternalServerError().body(format!("No DB entry"));
}

/// Get all Gases in the Date Range
#[get("/gas/range")]
async fn read_gas_range(
    state: web::Data<AppState>,
    date_range: web::Query<DateRange>,
) -> impl Responder {
    let Some(conn) = &state.conn else {
        return HttpResponse::InternalServerError().body(format!("No DB Connection"));
    };

    let start_date = date_range.start_date;
    let end_date = date_range.end_date;

    // Query between date range
    let gases = gas::Entity::find()
        .filter(gas::Column::Date.between(start_date, end_date))
        .all(conn)
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

/* #endregion */

/* #region PRESENCE */

/// Get Presence Sensor Value
#[get("/presence")]
async fn sensor_presence(state: web::Data<AppState>) -> impl Responder {
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

/* #region ALL SENSORS */

/// Get all sensors value
#[get("/status/sensors")]
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
    let Some(conn) = &state.conn else {
        return HttpResponse::InternalServerError().body(format!("No DB Connection"));
    };

    let mut response: Vec<Value> = vec![];

    // temp
    let temperature = get_latest_temp(conn).await;

    if let Some(temperature) = temperature {
        response.push(json!({
            "date": temperature.date.to_string(),
            "temperature_level": &temperature.temperature,
        }));
    }

    // humidity
    let humidity = get_latest_humidity(conn).await;

    if let Some(humidity) = humidity {
        response.push(json!({
            "date": humidity.date.to_string(),
            "humidity_level": &humidity.humidity,
        }));
    }

    // gas
    let gas = get_latest_gas_level(conn).await;

    if let Some(gas) = gas {
        response.push(json!({
            "date": gas.date.to_string(),
            "gas_level": gas.gas_level,
        }));
    }

    return HttpResponse::Ok().json(response);
}

/* #endregion */
