import Head from "next/head";
import { useRouter } from "next/router";
import { useState } from "react";

export default function Home() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [searchType, setSearchType] = useState("person");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!name.trim()) {
      setError("Introduceti un nume sau o entitate pentru cautare");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const backendUrl =
        process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
      const response = await fetch(`${backendUrl}/search`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: name.trim(),
          search_type: searchType,
        }),
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || "Cautarea a esuat");
      }

      const data = await response.json();
      sessionStorage.setItem("searchResults", JSON.stringify(data));
      router.push("/results");
    } catch (err) {
      console.error("Search error:", err);
      setError(err.message || "A aparut o eroare in timpul cautarii");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Head>
        <title>Verificare Sanctiuni | Conformitate</title>
        <meta
          name="description"
          content="Verificati persoane si entitati in bazele de date UE si ONU privind sanctiunile"
        />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" href="/favicon.ico" />
      </Head>

      <div className="page">
        <main className="container">
          <header className="page-header">
            <div className="logo">
              <div className="logo-icon">VS</div>
              <span className="logo-text">Verificare Sanctiuni</span>
            </div>
            <h1>Verificare Sanctiuni Internationale</h1>
            <p className="subtitle">
              Verificati persoanele si entitatile in bazele de date
              internationale cu colectare automata a dovezilor si analiza de
              risc.
            </p>
          </header>

          <section className="page-content">
            <form className="search-form card" onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label" htmlFor="name">
                  Nume sau Entitate
                </label>
                <input
                  type="text"
                  id="name"
                  className="form-input"
                  placeholder="Introduceti numele persoanei sau companiei..."
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={loading}
                  autoComplete="off"
                />
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="searchType">
                  Tip Cautare
                </label>
                <select
                  id="searchType"
                  className="form-select"
                  value={searchType}
                  onChange={(e) => setSearchType(e.target.value)}
                  disabled={loading}
                >
                  <option value="person">Persoana Fizica</option>
                  <option value="entity">Companie / Entitate</option>
                </select>
              </div>

              {error && (
                <div
                  style={{
                    padding: "12px",
                    background: "#fee2e2",
                    border: "1px solid #fecaca",
                    borderRadius: "6px",
                    color: "#dc2626",
                    marginBottom: "20px",
                    fontSize: "14px",
                  }}
                >
                  {error}
                </div>
              )}

              <button
                type="submit"
                className="btn btn-primary btn-lg btn-block"
                disabled={loading}
              >
                {loading ? (
                  <>
                    <div className="spinner"></div>
                    Se verifica...
                  </>
                ) : (
                  "Incepe Verificarea"
                )}
              </button>

              {loading && (
                <p
                  style={{
                    textAlign: "center",
                    marginTop: "14px",
                    color: "var(--color-gray-500)",
                    fontSize: "13px",
                  }}
                >
                  Se interogheaza bazele de date UE si ONU...
                </p>
              )}
            </form>

            <div className="features-grid">
              <div className="feature-card">
                <div className="feature-icon">UE</div>
                <h3 className="feature-title">Harta Sanctiunilor UE</h3>
                <p className="feature-desc">
                  Verificare in baza de date oficiala a masurilor restrictive UE
                </p>
              </div>

              <div className="feature-card">
                <div className="feature-icon">ONU</div>
                <h3 className="feature-title">Consiliul de Securitate ONU</h3>
                <p className="feature-desc">
                  Verificare in lista consolidata de sanctiuni ONU
                </p>
              </div>

              <div className="feature-card">
                <div className="feature-icon">AI</div>
                <h3 className="feature-title">Analiza de Risc</h3>
                <p className="feature-desc">
                  Evaluare automata a riscului si recomandari de conformitate
                </p>
              </div>
            </div>
          </section>

          <footer className="footer">
            <p>
              Verificare Sanctiuni | Arhitectura Stateless | Dovezi stocate in
              DigitalOcean Spaces
            </p>
          </footer>
        </main>
      </div>
    </>
  );
}
