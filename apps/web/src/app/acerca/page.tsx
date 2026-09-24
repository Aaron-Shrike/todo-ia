import type { Metadata } from "next";
import Link from "next/link";

import { SiteFooter, SiteHeader } from "@/components/SiteChrome";
import {
  ArrowRightIcon,
  CpuIcon,
  DatabaseIcon,
  GithubIcon,
  HexagonIcon,
  LayersIcon,
  ShieldCheckIcon,
  SparkleIcon,
} from "@/components/icons";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Acerca de — todo-ia",
  description:
    "Cómo todo-ia detecta frases semánticamente duplicadas antes de guardarlas, y cómo está construido.",
};

const REPO_URL = "https://github.com/Aaron-Shrike/todo-ia";

const FEATURES = [
  {
    Icon: SparkleIcon,
    title: "Detecta duplicados por significado, no por texto",
    text: "Compara cada frase nueva contra las guardadas usando un modelo real de embeddings — atrapa parafraseos y mezclas de idioma, no solo coincidencias exactas de caracteres.",
  },
  {
    Icon: LayersIcon,
    title: "Muestra todas las coincidencias, no solo la mejor",
    text: "Cuando hay un posible duplicado, la lista completa de frases similares está disponible con scroll infinito — nunca solo el resultado más parecido, truncado en silencio.",
  },
  {
    Icon: ShieldCheckIcon,
    title: "El servidor nunca confía en lo ya validado",
    text: "Cada guardado vuelve a comparar contra los datos actuales en el momento del guardado, bajo un bloqueo, incluso si ya validaste antes — un dato manipulado en el cliente no cambia el veredicto.",
  },
  {
    Icon: CpuIcon,
    title: "Modelo de embeddings local, sin llamadas externas",
    text: "El checkpoint de sentence-transformers corre dentro del propio contenedor, horneado en la imagen y anclado a una revisión exacta — offline y reproducible.",
  },
  {
    Icon: DatabaseIcon,
    title: "Postgres + pgvector, con dos formas de búsqueda",
    text: "Un índice HNSW aproximado responde rápido '¿cuál es la más parecida?'; un escaneo exacto decide qué realmente cuenta como duplicado — la decisión que se guarda nunca depende de una aproximación.",
  },
  {
    Icon: HexagonIcon,
    title: "Progreso narrado, nunca un spinner genérico",
    text: "'Validando...', 'Revalidando...', 'Guardando...' — cada etiqueta describe una llamada real en curso, y ninguna sobrevive a la respuesta que la originó.",
  },
];

const FLOW = [
  {
    title: "Escribís una frase",
    text: "El contador de caracteres y el límite se validan en el cliente antes de cualquier llamada.",
  },
  {
    title: "Se compara por significado",
    text: "El backend la convierte en un vector y calcula similitud coseno contra todas las frases guardadas.",
  },
  {
    title: "Te avisa si hay un parecido",
    text: "Si algo supera el umbral configurado, ves la frase más similar, el porcentaje y la lista completa de coincidencias.",
  },
  {
    title: "Vos decidís",
    text: "Guardás igual si es intencional, o cancelás — nada se guarda sin tu confirmación explícita.",
  },
];

const STACK = ["Next.js + TypeScript", "FastAPI", "PostgreSQL + pgvector", "sentence-transformers", "Docker Compose"];

const RISKS = [
  {
    title: "Los escaneos exactos crecen con los datos",
    text: "La búsqueda de coincidencias y la verificación al guardar recorren cada fila almacenada — aceptado a la escala actual, con tiempos medidos documentados.",
  },
  {
    title: "Las semánticas casi-duplicadas no tienen respaldo de base de datos",
    text: "El texto idéntico está protegido por un índice único; los casi-duplicados semánticos dependen del bloqueo de escritura y de la lógica de la aplicación.",
  },
];

export default function AcercaPage() {
  return (
    <main className={styles.page}>
      <SiteHeader />

      <section className={styles.hero}>
        <span className={styles.eyebrow}>IA aplicada · detección semántica</span>
        <h1 className={styles.heroTitle}>Una lista de frases que sabe cuándo ya dijiste lo mismo</h1>
        <p className={styles.heroLead}>
          todo-ia es una lista de frases cortas — como una lista de tareas, pero para oraciones —
          respaldada por detección semántica de duplicados: antes de guardar, el backend compara tu
          frase por significado contra todas las guardadas, usando un modelo real de embeddings, y te
          pide confirmar si encuentra algo muy parecido.
        </p>
        <div className={styles.heroActions}>
          <Link href="/" className={`${styles.button} ${styles.buttonPrimary}`}>
            Abrir la app
            <ArrowRightIcon width={18} height={18} />
          </Link>
          <a
            className={`${styles.button} ${styles.buttonGhost}`}
            href={REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
          >
            <GithubIcon width={18} height={18} />
            Ver el código
          </a>
        </div>
      </section>

      <section className={styles.section} aria-labelledby="que-hace">
        <div className={styles.sectionHead}>
          <h2 id="que-hace" className={styles.sectionTitle}>
            Qué hace
          </h2>
          <p className={styles.sectionLead}>
            Seis decisiones concretas sobre cómo se comporta la detección de duplicados.
          </p>
        </div>
        <div className={styles.grid}>
          {FEATURES.map(({ Icon, title, text }) => (
            <article className={styles.card} key={title}>
              <div className={styles.cardIcon}>
                <Icon />
              </div>
              <h3 className={styles.cardTitle}>{title}</h3>
              <p className={styles.cardText}>{text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.section} aria-labelledby="como-funciona">
        <div className={styles.sectionHead}>
          <h2 id="como-funciona" className={styles.sectionTitle}>
            Cómo funciona, de tu lado
          </h2>
          <p className={styles.sectionLead}>El flujo completo, en cuatro pasos.</p>
        </div>
        <ol className={styles.flow}>
          {FLOW.map((step) => (
            <li className={styles.flowStep} key={step.title}>
              <span className={styles.flowNumber} aria-hidden="true" />
              <h3 className={styles.flowTitle}>{step.title}</h3>
              <p className={styles.flowText}>{step.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className={styles.section} aria-labelledby="como-lo-hace">
        <div className={styles.sectionHead}>
          <h2 id="como-lo-hace" className={styles.sectionTitle}>
            Cómo está construido
          </h2>
          <p className={styles.sectionLead}>
            Arquitectura hexagonal en un monorepo: el dominio no importa el framework, y cada módulo
            publica su propio contrato.
          </p>
        </div>
        <div className={styles.stackRow}>
          {STACK.map((item) => (
            <span className={styles.stackItem} key={item}>
              <HexagonIcon />
              {item}
            </span>
          ))}
        </div>
      </section>

      <section className={styles.section} aria-labelledby="limitaciones">
        <div className={styles.sectionHead}>
          <h2 id="limitaciones" className={styles.sectionTitle}>
            Límites conocidos, documentados a propósito
          </h2>
          <p className={styles.sectionLead}>
            Ninguna decisión de diseño es gratis — estas son las que quedaron abiertas, por elección.
          </p>
        </div>
        {RISKS.map((risk) => (
          <div className={styles.risk} key={risk.title}>
            <p className={styles.riskTitle}>{risk.title}</p>
            <p className={styles.riskText}>{risk.text}</p>
          </div>
        ))}
      </section>

      <SiteFooter />
    </main>
  );
}
