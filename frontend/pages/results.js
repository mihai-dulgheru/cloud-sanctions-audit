import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

const backendUrl =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export default function Results() {
  const router = useRouter();
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [selectedPerson, setSelectedPerson] = useState(null);
  const [searching, setSearching] = useState(false);

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

  // Helper functions
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

  // Handler functions
  const handlePersonSelect = (person) => {
    setSelectedPerson(person);
    setShowConfirmation(true);
  };

  const handleConfirmSearch = async () => {
    if (!selectedPerson) return;

    setShowConfirmation(false);
    setSearching(true);

    try {
      const response = await fetch(`${backendUrl}/search`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: selectedPerson.name,
          search_type: results.search_type,
        }),
      });

      if (!response.ok) {
        throw new Error("Căutarea a eșuat");
      }

      const data = await response.json();
      sessionStorage.setItem("searchResults", JSON.stringify(data));
      setResults(data);
      setSearching(false);
    } catch (err) {
      console.error("Search error:", err);
      alert("A apărut o eroare în timpul căutării");
      setSearching(false);
    }
  };

  const handleCancelSearch = () => {
    setShowConfirmation(false);
    setSelectedPerson(null);
  };

  // Check if we should show person selection UI
  const shouldShowPersonSelection =
    results &&
    !results.eu_found &&
    !results.un_found &&
    results.eu_matches?.filter((m) => m.type === "person_match").length > 1;

  // Check if there's a high risk (person found in sanctions)
  const isHighRisk = results && (results.eu_found || results.un_found);

  // Show person selection UI if conditions are met
  if (shouldShowPersonSelection) {
    const personMatches = results.eu_matches.filter(
      (m) => m.type === "person_match",
    );

    return (
      <>
        <Head>
          <title>
            Selectați persoana - {results.query} | Verificare sancțiuni
          </title>
        </Head>

        <div className="page">
          <main className="container">
            <header className="page-header header-left-aligned">
              <Link href="/" className="back-link">
                ← Înapoi la căutare
              </Link>
              <h1 className="header-title-no-margin">
                Mai multe persoane găsite
              </h1>
              <p className="subtitle subtitle-no-max-width">
                Au fost găsite {personMatches.length} persoane care corespund
                căutării <strong>{results.query}</strong>. Selectați persoana
                corectă pentru a continua analiza.
              </p>
            </header>

            <section className="page-content">
              <div className="person-matches-grid">
                {personMatches.map((person, idx) => (
                  <div
                    key={idx}
                    className="person-match-card"
                    onClick={() => handlePersonSelect(person)}
                  >
                    <div className="person-match-icon">👤</div>
                    <div className="person-match-name">{person.name}</div>
                    <div className="person-match-action">Selectați →</div>
                  </div>
                ))}
              </div>
            </section>
          </main>
        </div>

        {showConfirmation && selectedPerson && (
          <div className="modal-overlay" onClick={handleCancelSearch}>
            <div className="modal-content" onClick={(e) => e.stopPropagation()}>
              <h2 className="modal-title">Confirmați analiza</h2>
              <p className="modal-text">
                Doriți să continuați cu analiza completă pentru:
              </p>
              <div className="modal-person-name">{selectedPerson.name}</div>
              <div className="modal-actions">
                <button
                  className="btn btn-secondary"
                  onClick={handleCancelSearch}
                >
                  Anulează
                </button>
                <button
                  className="btn btn-primary"
                  onClick={handleConfirmSearch}
                >
                  Continuă analiza
                </button>
              </div>
            </div>
          </div>
        )}

        {searching && (
          <div className="loading-overlay">
            <div className="loading-overlay-content">
              <div className="loading-animation">
                <div className="scan-line"></div>
                <div className="search-icon">🔍</div>
              </div>
              <h2 className="loading-overlay-title">Analiza în curs</h2>
              <p className="loading-overlay-text">
                Se analizează {selectedPerson?.name}...
              </p>
              <div className="loading-dots">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        )}
      </>
    );
  }

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

      <div className={`page ${isHighRisk ? "high-risk-page" : ""}`}>
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
            {isHighRisk && (
              <div className="risk-warning-banner">
                <div className="risk-warning-icon">⚠️</div>
                <div className="risk-warning-content">
                  <div className="risk-warning-title">
                    ATENȚIE: Risc ridicat detectat
                  </div>
                  <div className="risk-warning-text">
                    Această persoană/entitate a fost găsită în bazele de date cu
                    sancțiuni. Recomandăm precauție maximă în orice relație de
                    afaceri.
                  </div>
                </div>
              </div>
            )}

            <div
              className={`summary-card ${isHighRisk ? "summary-card-warning" : ""}`}
            >
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
              <div
                className={`result-card ${results.eu_found ? "result-card-danger" : ""}`}
              >
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

              <div
                className={`result-card ${results.un_found ? "result-card-danger" : ""}`}
              >
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
              <h2 className="evidence-title">📁 Fișiere audit</h2>
              <p className="evidence-description">
                Toate dovezile sunt stocate securizat în DigitalOcean Spaces.
                Link-urile expiră în 1 oră.
              </p>

              {results.audit_folder && (
                <div className="file-explorer">
                  <div className="folder-header">
                    <div className="folder-icon">📂</div>
                    <div className="folder-info">
                      <div className="folder-name">{results.audit_folder}/</div>
                    </div>
                  </div>

                  <div className="files-list">
                    {results.evidence_urls?.audit_log && (
                      <a
                        href={results.evidence_urls.audit_log}
                        download="audit_log.txt"
                        className="file-item"
                      >
                        <div className="file-icon text-file">📄</div>
                        <div className="file-info">
                          <div className="file-name">audit_log.txt</div>
                          <div className="file-meta">
                            Text • Jurnal complet audit
                          </div>
                        </div>
                        <div className="file-action">↓</div>
                      </a>
                    )}

                    {results.evidence_urls?.eu_evidence && (
                      <a
                        href={results.evidence_urls.eu_evidence}
                        download="evidence_eu.pdf"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="file-item"
                      >
                        <div className="file-icon pdf-file">📕</div>
                        <div className="file-info">
                          <div className="file-name">evidence_eu.pdf</div>
                          <div className="file-meta">
                            PDF • Dovadă sancțiuni UE
                          </div>
                        </div>
                        <div className="file-action">↓</div>
                      </a>
                    )}

                    {results.evidence_urls?.un_evidence && (
                      <a
                        href={results.evidence_urls.un_evidence}
                        download="evidence_un.pdf"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="file-item"
                      >
                        <div className="file-icon pdf-file">📘</div>
                        <div className="file-info">
                          <div className="file-name">evidence_un.pdf</div>
                          <div className="file-meta">
                            PDF • Dovadă sancțiuni ONU
                          </div>
                        </div>
                        <div className="file-action">↓</div>
                      </a>
                    )}

                    {results.evidence_urls?.raw_data && (
                      <a
                        href={results.evidence_urls.raw_data}
                        download="raw_data.json"
                        className="file-item"
                      >
                        <div className="file-icon json-file">📊</div>
                        <div className="file-info">
                          <div className="file-name">raw_data.json</div>
                          <div className="file-meta">JSON • Date brute API</div>
                        </div>
                        <div className="file-action">↓</div>
                      </a>
                    )}
                  </div>
                </div>
              )}
            </div>
          </section>
        </main>
      </div>
    </>
  );
}
