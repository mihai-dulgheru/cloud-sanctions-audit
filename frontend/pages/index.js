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
      setError("Introduceți un nume sau o companie pentru căutare");
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
          name: name.trim().toUpperCase(),
          search_type: searchType,
        }),
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || "Căutarea a eșuat");
      }

      const data = await response.json();
      sessionStorage.setItem("searchResults", JSON.stringify(data));
      router.push("/results");
    } catch (err) {
      console.error("Search error:", err);
      setError(err.message || "A apărut o eroare în timpul căutării");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Head>
        <title>Verificare sancțiuni</title>
        <meta
          name="description"
          content="Verificați persoane și entități în bazele de date UE și ONU privind sancțiunile"
        />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" href="/favicon.ico" />
      </Head>

      <div className="page">
        <main className="container">
          <header className="page-header">
            <div className="logo">
              <div className="logo-icon">VS</div>
              <span className="logo-text">Verificare sancțiuni</span>
            </div>
            <h1>Verificare sancțiuni internaționale</h1>
            <p className="subtitle">
              Verificați persoanele și entitățile în bazele de date
              internaționale cu colectare automată a dovezilor și analiza de
              risc.
            </p>
          </header>

          <section className="page-content">
            <form className="search-form card" onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label" htmlFor="name">
                  Nume
                </label>
                <input
                  type="text"
                  id="name"
                  className="form-input"
                  placeholder="Introduceți numele persoanei sau companiei..."
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={loading}
                  autoComplete="off"
                />
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="searchType">
                  Tip căutare
                </label>
                <select
                  id="searchType"
                  className="form-select"
                  value={searchType}
                  onChange={(e) => setSearchType(e.target.value)}
                  disabled={loading}
                >
                  <option value="person">Persoană fizică</option>
                  <option value="entity">Companie</option>
                </select>
              </div>

              {error && <div className="error-message">{error}</div>}

              <button
                type="submit"
                className="btn btn-primary btn-lg btn-block"
                disabled={loading}
              >
                {loading ? (
                  <>
                    <div className="spinner"></div>
                    Se verifică...
                  </>
                ) : (
                  "Începe verificarea"
                )}
              </button>

              {loading && (
                <p className="loading-text">
                  Se interoghează bazele de date UE și ONU...
                </p>
              )}
            </form>
          </section>
        </main>
      </div>
    </>
  );
}
