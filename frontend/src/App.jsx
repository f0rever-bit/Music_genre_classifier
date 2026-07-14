import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ThemeProvider } from "./utils/ThemeContext";
import { AuthProvider } from "./utils/AuthContext";
import { PlayerProvider } from "./context/PlayerContext";
import { ToastProvider } from "./components/ui/toast";
import { TooltipProvider } from "./components/ui/tooltip";
import ProtectedRoute from "./components/ProtectedRoute";
import AppLayout from "./components/AppLayout";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import DashboardPage from "./pages/DashboardPage";
import UploadPage from "./pages/UploadPage";
import BulkUploadPage from "./pages/BulkUploadPage";
import AnalyzePage from "./pages/AnalyzePage";
import RecommendationsPage from "./pages/RecommendationsPage";
import AdminDashboardPage from "./pages/AdminDashboardPage";
import CallbackPage from "./pages/CallbackPage";
import SettingsPage from "./pages/SettingsPage";
import GlobalPlayer from "./components/GlobalPlayer";

export default function App() {
  const { i18n, t } = useTranslation();

  useEffect(() => {
    document.documentElement.lang = i18n.language || "en";
    document.title = t("common.appName");
    
    const handleLangChange = (lng) => {
      document.documentElement.lang = lng;
      document.title = t("common.appName");
    };
    
    i18n.on("languageChanged", handleLangChange);
    return () => {
      i18n.off("languageChanged", handleLangChange);
    };
  }, [i18n, i18n.language, t]);

  return (
    <ThemeProvider>
      <AuthProvider>
        <PlayerProvider>
          <ToastProvider>
            <TooltipProvider delayDuration={200}>
              <BrowserRouter>
                <Routes>
                  <Route path="/login" element={<LoginPage />} />
                  <Route path="/register" element={<RegisterPage />} />
                  <Route path="/callback" element={<CallbackPage />} />

                  <Route
                    element={
                      <ProtectedRoute>
                        <AppLayout />
                      </ProtectedRoute>
                    }
                  >
                    <Route path="/" element={<DashboardPage />} />
                    <Route path="/upload" element={<UploadPage />} />
                    <Route path="/bulk-upload" element={<BulkUploadPage />} />
                    <Route path="/analyze/:musicId" element={<AnalyzePage />} />
                    <Route path="/recommendations" element={<RecommendationsPage />} />
                    <Route path="/recommendations/:musicId" element={<RecommendationsPage />} />
                    <Route path="/settings" element={<SettingsPage />} />
                    <Route
                      path="/admin"
                      element={
                        <ProtectedRoute requireSuperuser>
                          <AdminDashboardPage />
                        </ProtectedRoute>
                      }
                    />
                  </Route>

                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </BrowserRouter>
            </TooltipProvider>
          </ToastProvider>
        </PlayerProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
