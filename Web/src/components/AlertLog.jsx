export default function AlertLog({ alerts }) {
  return (
    <section className="log">
      <h2>Journal des Alertes</h2>
      <ul>
        {alerts.length === 0 ? (
          <li className="log-item" style={{ borderColor: 'var(--green)', color: 'var(--muted)' }}>
            <strong>[OK]</strong> Aucun événement critique à signaler
          </li>
        ) : (
          alerts.map((a) => (
            <li key={a.id} className={`log-item ${a.level}`}>
              <strong>[{a.time}]</strong> {a.message}
            </li>
          ))
        )}
      </ul>
    </section>
  );
}