import { useEffect, useState, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Plot from "react-plotly.js";
import { motion } from "framer-motion";
import {
  Waveform,
  Play,
  Sparkle,
  Spinner,
  Gauge,
  Waves,
  SpeakerHigh,
  Lightning,
  Smiley,
} from "@phosphor-icons/react";
import { analyzeAPI, musicAPI } from "../services/api";
import { useAuth } from "../utils/AuthContext";
import { usePlayer } from "../context/PlayerContext";
import { useTheme } from "../utils/ThemeContext";
import { useToast } from "../components/ui/toast";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import StatusBadge from "../components/StatusBadge";
import { Badge } from "../components/ui/badge";
import CoverArt from "../components/CoverArt";

const clamp01 = (v) => {
  const n = Number(v);
  if (Number.isNaN(n)) return 0;
  return Math.max(0, Math.min(1, n));
};
const norm = (v, min, max) => clamp01((Number(v) - min) / (max - min));

// Pitch Class → standard key name (handles null/undefined and the falsy 0 case)
const KEY_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const keyName = (k) => {
  if (k === null || k === undefined || k === "") return "—";
  return KEY_NAMES[Number(k)] ?? "—";
};

function StatTile({ icon: Icon, label, value, unit }) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Icon className="h-4 w-4" />
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
      </div>
      <p className="mt-2 text-2xl font-semibold tabular-nums">
        {value}
        {unit && <span className="ml-1 text-sm font-normal text-muted-foreground">{unit}</span>}
      </p>
    </Card>
  );
}

export default function AnalyzePage() {
  const { musicId } = useParams();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { playTrack } = usePlayer();
  const { theme } = useTheme();
  const { toast } = useToast();

  const [track, setTrack] = useState(null);
  const [features, setFeatures] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");

    // Retry transient failures (5xx / network).  Render's free tier and
    // other cold-start proxies occasionally answer with 502/504, which is
    // not a real error — one retry usually succeeds.
    const fetchWithRetry = async (fn, attempts = 3) => {
      let lastErr;
      for (let i = 0; i < attempts; i++) {
        try {
          return await fn();
        } catch (err) {
          lastErr = err;
          const status = err?.response?.status;
          // Don't retry hard client errors (4xx except 429).
          if (status && status >= 400 && status < 500 && status !== 429) break;
          await new Promise((r) => setTimeout(r, 800 * (i + 1)));
        }
      }
      throw lastErr;
    };

    (async () => {
      // 1. Resolve the track first so we have its slug/id and status.
      let tr = null;
      try {
        const res = await fetchWithRetry(() => musicAPI.getById(musicId));
        tr = res?.data || null;
      } catch (err) {
        if (!active) return;
        const status = err?.response?.status;
        if (status === 404) {
          setTrack(null);
        } else {
          setError(t("analyze.loadError"));
        }
        setLoading(false);
        return;
      }
      if (!active) return;
      setTrack(tr);

      // 2. Drive the analysis to completion.  A freshly uploaded track is
      //    'pending' (background job may have been killed on a cloud host
      //    restart) — kick it off.  While 'analyzing', just poll.  Only ask
      //    for features once the status is terminal, so we never hit
      //    /features before the AudioFeatures row exists (which 404s).
      if (tr.analysis_status === "pending") {
        try {
          await analyzeAPI.analyze(musicId);
        } catch {
          // If the explicit analyze failed, fall through to polling — the
          // server may still be working via its own recovery path.
        }
      }
      if (tr.analysis_status !== "ready" && tr.analysis_status !== "error") {
        try {
          tr = await musicAPI.waitForAnalysis(musicId, {
            onUpdate: (u) => active && setTrack(u),
          });
        } catch {
          tr = tr || null;
        }
        if (!active) return;
        setTrack(tr);
      }

      // 3. Fetch features only once we know the terminal state.
      if (tr.analysis_status === "ready") {
        try {
          const fe = await fetchWithRetry(() => analyzeAPI.getFeatures(musicId));
          if (active) setFeatures(fe?.data || null);
        } catch {
          if (active) setFeatures(null);
        }
      } else if (tr.analysis_status === "error") {
        if (active) setError(tr.analysis_error || t("analyze.analysisFailed"));
      }
    })();
    return () => {
      active = false;
    };
  }, [musicId, t]);

  const chartLayout = useMemo(() => {
    const dark = theme === "dark";
    const gridAlpha = dark ? "rgba(161,161,170,0.15)" : "rgba(82,82,91,0.12)";
    const zeroAlpha = dark ? "rgba(161,161,170,0.25)" : "rgba(82,82,91,0.2)";
    return {
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      font: { color: dark ? "#a1a1aa" : "#52525b", family: "Geist Variable, sans-serif", size: 11 },
      margin: { t: 30, r: 24, b: 40, l: 24 },
      autosize: true,
      xaxis: { gridcolor: gridAlpha, zerolinecolor: zeroAlpha, tickfont: { size: 10 } },
      yaxis: { gridcolor: gridAlpha, zerolinecolor: zeroAlpha, tickfont: { size: 10 } },
      hoverlabel: {
        bgcolor: dark ? "#18181b" : "#ffffff",
        font: { color: dark ? "#e4e4e7" : "#09090b", family: "Geist Variable, sans-serif" },
        bordercolor: dark ? "#27272a" : "#e4e4e7",
      },
    };
  }, [theme]);

  const config = { displayModeBar: false, responsive: true };

  const radarData = useMemo(() => {
    const f = features || {};
    return [
      {
        type: "scatterpolar",
        r: [
          norm(f.energy, 0, 1),
          norm(f.valence, 0, 1),
          norm(f.tempo, 0, 250),
          norm(f.loudness, -60, 0),
          norm(f.spectral_centroid_mean ?? f.brightness, 0, 4000),
          norm(f.zero_crossing_rate_mean ?? f.zero_crossing_rate, 0, 0.2),
        ],
        theta: ["Energy", "Valence", "Tempo", "Loudness", "Brightness", "ZCR"],
        fill: "toself",
        hoveron: "points",
        line: { color: "#10b981", width: 2 },
        fillcolor: "rgba(16,185,129,0.18)",
        name: "profile",
        hovertemplate: "<b>%{theta}</b><br>Value: %{r:.1%}<extra></extra>",
      },
    ];
  }, [features]);

  // Radar-specific layout (larger margins to prevent label clipping)
  const radarLayout = useMemo(() => {
    const dark = theme === "dark";
    const gridAlpha = dark ? "rgba(161,161,170,0.18)" : "rgba(82,82,91,0.14)";
    return {
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      font: { color: dark ? "#a1a1aa" : "#52525b", family: "Geist Variable, sans-serif", size: 11 },
      margin: { t: 40, r: 50, b: 40, l: 50 },
      autosize: true,
      polar: {
        bgcolor: "transparent",
        radialaxis: {
          visible: true,
          range: [0, 1],
          gridcolor: gridAlpha,
          linecolor: gridAlpha,
          tickfont: { size: 9 },
          tickformat: ".0%",
        },
        angularaxis: {
          tickfont: { size: 11 },
          gridcolor: gridAlpha,
          linecolor: gridAlpha,
        },
      },
      hoverlabel: {
        bgcolor: dark ? "#18181b" : "#ffffff",
        font: { color: dark ? "#e4e4e7" : "#09090b", family: "Geist Variable, sans-serif" },
        bordercolor: dark ? "#27272a" : "#e4e4e7",
      },
    };
  }, [theme]);

  const mfccData = useMemo(() => {
    const arr = features?.mfcc_mean || features?.mfcc || [];
    return [
      {
        type: "bar",
        x: arr.map((_, i) => `C${i}`),
        y: arr,
        marker: { color: "#10b981" },
        name: "mfcc",
        hovertemplate: "<b>%{x}</b><br>Mean: %{y:.3f}<extra></extra>",
      },
    ];
  }, [features]);

  const chromaData = useMemo(() => {
    const arr = features?.chroma_stft_mean || features?.chroma || [];
    const labels = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
    return [
      {
        type: "bar",
        x: arr.map((_, i) => labels[i] || `P${i}`),
        y: arr,
        marker: { color: "#0ea5e9" },
        name: "chroma",
        hovertemplate: "<b>Pitch %{x}</b><br>Intensity: %{y:.3f}<extra></extra>",
      },
    ];
  }, [features]);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-80 rounded-xl" />
      </div>
    );
  }

  if (error || !track) {
    return (
      <div className="rounded-xl border border-border bg-card p-10 text-center">
        <p className="text-sm text-muted-foreground">{error || t("common.error")}</p>
        <Button variant="outline" className="mt-4" onClick={() => navigate("/")}>
          {t("common.back")}
        </Button>
      </div>
    );
  }

  const isSpotify = track.source === "spotify" || Boolean(track.spotify_track_id || track.spotifyTrackId || track.external_id);
  const f = features || {};
  const canPlay = isSpotify || track.analysis_status === "ready";

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
        className="flex flex-col sm:flex-row sm:items-center justify-between gap-4"
      >
        <div className="flex min-w-0 items-center gap-4">
          <CoverArt src={track.cover_url} className="h-14 w-14 shrink-0 rounded-2xl" />
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-semibold tracking-tight">{track.title}</h1>
            <p className="truncate text-sm text-muted-foreground">{track.artist}</p>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <StatusBadge status={track.analysis_status} />
              {track.genre && (
                <Badge variant="outline" className="pointer-events-none capitalize">
                  {track.genre}
                </Badge>
              )}
            </div>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button variant="outline" className="gap-2" onClick={() => playTrack(track)} disabled={!canPlay}>
            <Play className="h-4 w-4" />
            {t("analyze.playLocal")}
          </Button>
          <Button className="gap-2" onClick={() => navigate(`/recommendations/${track.slug || musicId}`)}>
            <Sparkle className="h-4 w-4" />
            {t("analyze.recommendations")}
          </Button>
        </div>
      </motion.div>

      {!features ? (
        <div className="rounded-xl border border-dashed border-border bg-card/50 p-12 text-center">
          <Spinner className="mx-auto mb-3 h-6 w-6 animate-spin text-muted-foreground" />
          <p className="text-sm text-muted-foreground">{t("analyze.noData")}</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
            <StatTile icon={Gauge} label={t("analyze.tempo")} value={Math.round(f.tempo || 0)} unit="BPM" />
            <StatTile icon={Waves} label={t("analyze.key")} value={keyName(f.key)} />
            <StatTile icon={Waves} label={t("analyze.loudness")} value={Math.round(f.loudness || 0)} unit="dB" />
            <StatTile icon={Lightning} label={t("analyze.energy")} value={Math.round((f.energy || 0) * 100)} unit="%" />
            <StatTile icon={Smiley} label={t("analyze.valence")} value={Math.round((f.valence || 0) * 100)} unit="%" />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">{t("analyze.radarTitle")}</CardTitle>
              </CardHeader>
              <CardContent>
                <Plot
                  data={radarData}
                  layout={radarLayout}
                  config={config}
                  style={{ width: "100%", height: 320 }}
                  useResizeHandler
                />
              </CardContent>
            </Card>

            {!(f.mfcc_mean && f.mfcc_mean.length > 0 && f.mfcc_mean.some(v => v !== 0)) ? (
              <Card className="col-span-1 lg:col-span-2">
                <CardContent className="flex items-center justify-center py-12 text-center">
                  <p className="text-sm text-muted-foreground">
                    {t("analyze.spotifyNoWaveform")}
                  </p>
                </CardContent>
              </Card>
            ) : (
              <>
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm">{t("analyze.mfccTitle")}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <Plot
                      data={mfccData}
                      layout={chartLayout}
                      config={config}
                      style={{ width: "100%", height: 300 }}
                      useResizeHandler
                    />
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm">{t("analyze.chromaTitle")}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <Plot
                      data={chromaData}
                      layout={chartLayout}
                      config={config}
                      style={{ width: "100%", height: 300 }}
                      useResizeHandler
                    />
                  </CardContent>
                </Card>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
