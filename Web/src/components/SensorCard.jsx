export default function SensorCard({ name, code, value, unit, alert }) {
  return (
    <div className={alert ? "card alert" : "card"}>
      <div className="card-head">
        <span className="card-code">{code}</span>
        <h3>{name}</h3>
      </div>
      <p className="card-value">
        {value}
        <small>{unit}</small>
      </p>
      <span className="card-state">{alert ? "⚠ ALERTE" : "● NOMINAL"}</span>
    </div>
  );
}