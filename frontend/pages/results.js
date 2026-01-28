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
      <div className="page loading-container">
        <div className="spinner loading-spinner-large"></div>
      </div>
    );
  }

  const getRiskBadgeClass = (risk) => {
    if (!risk) {
      return "badge-low";
    }
    const r = risk.toUpperCase();
    if (r === "CRITICAL" || r === "CRITIC") {
      return "badge-critical";
    }
    if (r === "HIGH" || r === "RIDICAT") {
      return "badge-high";
    }
    if (r === "MEDIUM" || r === "MEDIU") {
      return "badge-medium";
    }
    return "badge-low";
  };

  const getRiskLabel = (risk) => {
    if (!risk) {
      return "SCĂZUT";
    }
    const r = risk.toUpperCase();
    if (r === "CRITICAL") {
      return "CRITIC";
    }
    if (r === "HIGH") {
      return "RIDICAT";
    }
    if (r === "MEDIUM") {
      return "MEDIU";
    }
    if (r === "LOW") {
      return "SCĂZUT";
    }
    return risk;
  };

  const getSearchTypeLabel = (type) => {
    return type === "person" ? "Persoană" : "Companie";
  };

  return (
    <>
      <Head>
        <title>Rezultate - {results.query} | Verificare sancțiuni</title>
        <meta
          name="description"
          content={`Rezultatele verificării pentru ${results.query}`}
        />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

      <div className="page">
        <main className="container">
          <header className="page-header header-left-aligned">
            <Link href="/" className="back-link">
              ← Înapoi la căutare
            </Link>
            <div className="header-title-row">
              <h1 className="header-title-no-margin">
                Rezultatele verificării
              </h1>
              <span
                className={`badge ${getRiskBadgeClass(results.risk_score)}`}
              >
                Risc {getRiskLabel(results.risk_score)}
              </span>
            </div>
            <p className="subtitle subtitle-no-max-width">
              Interogare: <strong>{results.query}</strong> | Tip:{" "}
              <strong>{getSearchTypeLabel(results.search_type)}</strong>
            </p>
          </header>

          <section className="page-content">
            <div className="summary-card">
              <div className="summary-header">
                <div className="summary-title">Analiza de risc</div>
                <span
                  className={`badge ${getRiskBadgeClass(results.risk_score)}`}
                >
                  {getRiskLabel(results.risk_score)}
                </span>
              </div>
              <p className="summary-text">
                {results.ai_summary || "Nu există analiza disponibilă."}
              </p>
            </div>

            <div className="results-grid">
              <div className="result-card">
                <div className="result-card-header">
                  <div className="result-card-title">
                    <div className="result-card-icon eu">UE</div>
                    Harta Sancțiunilor UE
                  </div>
                  <span
                    className={`badge ${results.eu_found ? "badge-high" : "badge-low"}`}
                  >
                    {results.eu_found ? "GĂSIT" : "NEGĂSIT"}
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
                                  Persoană găsită în sancțiunile UE
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
                                    <span> | Țara: {match.country}</span>
                                  )}
                                </div>
                                {match.measures?.length > 0 && (
                                  <div className="match-measures">
                                    Măsuri:{" "}
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
                      <p>Nicio potrivire în baza de date UE</p>
                    </div>
                  )}
                </div>
              </div>

              <div className="result-card">
                <div className="result-card-header">
                  <div className="result-card-title">
                    <div className="result-card-icon un">ONU</div>
                    Consiliul de Securitate ONU
                  </div>
                  <span
                    className={`badge ${results.un_found ? "badge-high" : "badge-low"}`}
                  >
                    {results.un_found ? "GĂSIT" : "NEGĂSIT"}
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
                    </>
                  ) : (
                    <div className="no-match">
                      <p>Nicio potrivire în lista consolidată ONU</p>
                    </div>
                  )}
                </div>
              </div>
            </div>

            <div className="evidence-section">
              <h2 className="evidence-title">Fișiere dovezi audit</h2>
              <p className="evidence-description">
                Toate dovezile sunt stocate securizat. Link-urile expiră în 1
                oră.
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
                      <div className="evidence-link-title">Dovadă UE</div>
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
                      <div className="evidence-link-title">Dovadă ONU</div>
                      <div className="evidence-link-desc">evidence_un.pdf</div>
                    </div>
                  </a>
                )}
              </div>

              {results.audit_folder && (
                <p className="storage-path">
                  Cale stocare: {results.audit_folder}/
                </p>
              )}
            </div>
          </section>
        </main>
      </div>
    </>
  );
}
