import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

export default function Results() {
  const router = useRouter();
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored = sessionStorage.getItem("searchResults");
    if (stored) {
      try {
        setResults(JSON.parse(stored));
      } catch (e) {
        console.error("Failed to parse results:", e);
        router.push("/");
      }
    } else {
      router.push("/");
    }
    setLoading(false);
  }, [router]);

  if (loading || !results) {
    return (
      <div
        className="page"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div
          className="spinner"
          style={{ width: "40px", height: "40px", borderWidth: "3px" }}
        ></div>
      </div>
    );
  }

  const getRiskBadgeClass = (risk) => {
    if (!risk) return "badge-low";
    const r = risk.toUpperCase();
    if (r === "CRITICAL" || r === "CRITIC") return "badge-critical";
    if (r === "HIGH" || r === "RIDICAT") return "badge-high";
    if (r === "MEDIUM" || r === "MEDIU") return "badge-medium";
    return "badge-low";
  };

  const getRiskLabel = (risk) => {
    if (!risk) return "SCAZUT";
    const r = risk.toUpperCase();
    if (r === "CRITICAL") return "CRITIC";
    if (r === "HIGH") return "RIDICAT";
    if (r === "MEDIUM") return "MEDIU";
    if (r === "LOW") return "SCAZUT";
    return risk;
  };

  const getSearchTypeLabel = (type) => {
    return type === "person" ? "Persoana" : "Entitate";
  };

  return (
    <>
      <Head>
        <title>Rezultate - {results.query} | Verificare Sanctiuni</title>
        <meta
          name="description"
          content={`Rezultatele verificarii pentru ${results.query}`}
        />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

      <div className="page">
        <main className="container">
          <header
            className="page-header"
            style={{ textAlign: "left", paddingBottom: "16px" }}
          >
            <Link href="/" className="back-link">
              ← Inapoi la Cautare
            </Link>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "12px",
                flexWrap: "wrap",
              }}
            >
              <h1 style={{ marginBottom: 0 }}>Rezultatele Verificarii</h1>
              <span
                className={`badge ${getRiskBadgeClass(results.risk_score)}`}
              >
                Risc {getRiskLabel(results.risk_score)}
              </span>
            </div>
            <p
              className="subtitle"
              style={{ margin: "10px 0 0 0", maxWidth: "none" }}
            >
              Interogare: <strong>{results.query}</strong> | Tip:{" "}
              <strong>{getSearchTypeLabel(results.search_type)}</strong>
            </p>
          </header>

          <section className="page-content">
            {/* Summary Card */}
            <div className="summary-card">
              <div className="summary-header">
                <div className="summary-title">Analiza de Risc</div>
                <span
                  className={`badge ${getRiskBadgeClass(results.risk_score)}`}
                >
                  {getRiskLabel(results.risk_score)}
                </span>
              </div>
              <p className="summary-text">
                {results.ai_summary || "Nu exista analiza disponibila."}
              </p>
            </div>

            {/* Results Grid */}
            <div className="results-grid">
              {/* EU Sanctions Card */}
              <div className="result-card">
                <div className="result-card-header">
                  <div className="result-card-title">
                    <div className="result-card-icon eu">UE</div>
                    Harta Sanctiunilor UE
                  </div>
                  <span
                    className={`badge ${results.eu_found ? "badge-high" : "badge-low"}`}
                  >
                    {results.eu_found ? "GASIT" : "NEGASIT"}
                  </span>
                </div>
                <div className="result-card-body">
                  {results.eu_found && results.eu_matches?.length > 0 ? (
                    <>
                      <ul className="match-list">
                        {results.eu_matches.slice(0, 5).map((match, idx) => (
                          <li key={idx} className="match-item">
                            {match.type === "person_match" ? (
                              <>
                                <div className="match-name">{match.name}</div>
                                <div className="match-details">
                                  Persoana gasita in sanctiunile UE
                                </div>
                              </>
                            ) : (
                              <>
                                <div className="match-name">
                                  {match.acronym || "Regim"}
                                </div>
                                <div className="match-details">
                                  {match.specification && (
                                    <span>
                                      {match.specification.substring(0, 100)}...
                                    </span>
                                  )}
                                  {match.country && (
                                    <span> | Tara: {match.country}</span>
                                  )}
                                </div>
                                {match.measures?.length > 0 && (
                                  <div
                                    style={{
                                      marginTop: "6px",
                                      fontSize: "12px",
                                      color: "var(--color-gray-500)",
                                    }}
                                  >
                                    Masuri:{" "}
                                    {match.measures.filter(Boolean).join(", ")}
                                  </div>
                                )}
                              </>
                            )}
                          </li>
                        ))}
                      </ul>
                    </>
                  ) : (
                    <div className="no-match">
                      <p>Nicio potrivire in baza de date UE</p>
                    </div>
                  )}
                </div>
              </div>

              {/* UN Security Council Card */}
              <div className="result-card">
                <div className="result-card-header">
                  <div className="result-card-title">
                    <div className="result-card-icon un">ONU</div>
                    Consiliul de Securitate ONU
                  </div>
                  <span
                    className={`badge ${results.un_found ? "badge-high" : "badge-low"}`}
                  >
                    {results.un_found ? "GASIT" : "NEGASIT"}
                  </span>
                </div>
                <div className="result-card-body">
                  {results.un_found && results.un_matches?.length > 0 ? (
                    <>
                      <ul className="match-list">
                        {results.un_matches.slice(0, 5).map((match, idx) => (
                          <li key={idx} className="match-item">
                            <div className="match-name">
                              {match.name || "Necunoscut"}
                            </div>
                            <div className="match-details">
                              {match.reference_number && (
                                <span>Ref: {match.reference_number}</span>
                              )}
                              {match.listed_on && (
                                <span> | Listat: {match.listed_on}</span>
                              )}
                            </div>
                          </li>
                        ))}
                      </ul>
                      {results.evidence_urls?.un_evidence && (
                        <div className="iframe-container">
                          <iframe
                            src={results.evidence_urls.un_evidence}
                            title="Dovada Sanctiuni ONU"
                          />
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="no-match">
                      <p>Nicio potrivire in lista consolidata ONU</p>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Evidence Section */}
            <div className="evidence-section">
              <h2 className="evidence-title">Fisiere Dovezi Audit</h2>
              <p
                style={{
                  color: "var(--color-gray-500)",
                  marginBottom: "16px",
                  fontSize: "13px",
                }}
              >
                Toate dovezile sunt stocate securizat. Link-urile expira in 1
                ora.
              </p>
              <div className="evidence-grid">
                {results.evidence_urls?.eu_evidence && (
                  <a
                    href={results.evidence_urls.eu_evidence}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="evidence-link"
                  >
                    <div className="evidence-link-icon">PDF</div>
                    <div className="evidence-link-text">
                      <div className="evidence-link-title">Dovada UE</div>
                      <div className="evidence-link-desc">evidence_eu.pdf</div>
                    </div>
                  </a>
                )}

                {results.evidence_urls?.un_evidence && (
                  <a
                    href={results.evidence_urls.un_evidence}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="evidence-link"
                  >
                    <div className="evidence-link-icon">PDF</div>
                    <div className="evidence-link-text">
                      <div className="evidence-link-title">Dovada ONU</div>
                      <div className="evidence-link-desc">evidence_un.pdf</div>
                    </div>
                  </a>
                )}

                {results.evidence_urls?.raw_data && (
                  <a
                    href={results.evidence_urls.raw_data}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="evidence-link"
                  >
                    <div className="evidence-link-icon">JSON</div>
                    <div className="evidence-link-text">
                      <div className="evidence-link-title">Date Brute</div>
                      <div className="evidence-link-desc">raw_data.json</div>
                    </div>
                  </a>
                )}

                {results.evidence_urls?.audit_log && (
                  <a
                    href={results.evidence_urls.audit_log}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="evidence-link"
                  >
                    <div className="evidence-link-icon">TXT</div>
                    <div className="evidence-link-text">
                      <div className="evidence-link-title">Jurnal Audit</div>
                      <div className="evidence-link-desc">audit_log.txt</div>
                    </div>
                  </a>
                )}
              </div>

              {results.audit_folder && (
                <p
                  style={{
                    marginTop: "16px",
                    color: "var(--color-gray-500)",
                    fontSize: "12px",
                    fontFamily: "monospace",
                  }}
                >
                  Cale Stocare: {results.audit_folder}/
                </p>
              )}
            </div>

            {/* Actions */}
            <div
              style={{
                display: "flex",
                gap: "12px",
                marginTop: "40px",
                justifyContent: "center",
                flexWrap: "wrap",
              }}
            >
              <Link href="/" className="btn btn-primary btn-lg">
                Cautare Noua
              </Link>
              <button
                className="btn btn-secondary btn-lg"
                onClick={() => window.print()}
              >
                Printeaza Raport
              </button>
            </div>
          </section>

          <footer className="footer">
            <p>Verificare Sanctiuni | Folder Audit: {results.audit_folder}</p>
          </footer>
        </main>
      </div>
    </>
  );
}
