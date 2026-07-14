import { useEffect, useState, useCallback } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../utils/AuthContext";
import {
  MusicNotes,
  House,
  Sparkle,
  UploadSimple,
  Files,
  Shield,
  UserCircle,
  SignOut,
  ListPlus,
  Gear,
  List,
  X,
} from "@phosphor-icons/react";
import ThemeToggle from "./ThemeToggle";
import LanguageSwitcher from "./LanguageSwitcher";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "./ui/dropdown-menu";
import { Button } from "./ui/button";

export default function Navbar() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const closeMobile = useCallback(() => setMobileOpen(false), []);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 4);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Close mobile menu on route change
  useEffect(() => {
    closeMobile();
  }, [location.pathname, closeMobile]);

  // Close mobile menu when viewport grows past md breakpoint
  useEffect(() => {
    const onResize = () => {
      if (window.innerWidth >= 768) closeMobile();
    };
    window.addEventListener("resize", onResize, { passive: true });
    return () => window.removeEventListener("resize", onResize);
  }, [closeMobile]);

  // Prevent body scroll when mobile menu is open
  useEffect(() => {
    document.body.style.overflow = mobileOpen ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [mobileOpen]);

  const handleLogout = async () => {
    closeMobile();
    await logout();
    navigate("/login");
  };

  const navLinkClass = ({ isActive }) =>
    `inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
      isActive
        ? "bg-accent text-accent-foreground"
        : "text-muted-foreground hover:text-foreground hover:bg-accent/60"
    }`;

  const mobileLinkClass = ({ isActive }) =>
    `flex items-center gap-3 rounded-lg px-4 py-3 text-base font-medium transition-colors ${
      isActive
        ? "bg-accent text-accent-foreground"
        : "text-muted-foreground hover:text-foreground hover:bg-accent/60"
    }`;

  const mobileItemClick = (to) => () => {
    closeMobile();
    navigate(to);
  };

  return (
    <>
    <header
      className={`sticky top-0 z-40 h-16 w-full border-b backdrop-blur transition-colors ${
        scrolled ? "border-border bg-background/80" : "border-transparent bg-background/40"
      }`}
    >
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-2 px-4">
        <Link to="/" className="mr-2 flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <MusicNotes className="h-[18px] w-[18px]" weight="fill" />
          </span>
          <span className="text-base font-semibold tracking-tight">{t("common.appName")}</span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden items-center gap-1 md:flex">
          <NavLink to="/" end className={navLinkClass}>
            <House className="h-4 w-4" />
            {t("nav.dashboard")}
          </NavLink>
          <NavLink to="/recommendations" className={navLinkClass}>
            <Sparkle className="h-4 w-4" />
            {t("nav.recommendations")}
          </NavLink>
          {user?.is_superuser && (
            <NavLink to="/admin" className={navLinkClass}>
              <Shield className="h-4 w-4" />
              {t("nav.admin")}
            </NavLink>
          )}
        </nav>

        {/* Hamburger button — visible only below md */}
        <button
          type="button"
          className="ml-auto inline-flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:hidden"
          onClick={() => setMobileOpen((v) => !v)}
          aria-label={mobileOpen ? t("common.close") : t("nav.menu")}
          aria-expanded={mobileOpen}
        >
          {mobileOpen ? <X className="h-5 w-5" /> : <List className="h-5 w-5" />}
        </button>

        {/* Desktop right-side controls — hidden below md */}
        <div className="ml-auto hidden items-center gap-1.5 md:flex">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="sm" className="gap-2">
                <UploadSimple className="h-4 w-4" />
                <span className="hidden sm:inline">{t("nav.upload")}</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => navigate("/upload")}>
                <UploadSimple className="h-4 w-4" />
                {t("upload.fromFile")}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => navigate("/bulk-upload")}>
                <Files className="h-4 w-4" />
                {t("nav.bulkUpload")}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => navigate("/upload?tab=spotify")}>
                <ListPlus className="h-4 w-4" />
                {t("upload.fromSpotify")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <LanguageSwitcher />
          <ThemeToggle />

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="inline-flex h-9 items-center gap-2 rounded-lg px-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.98]">
                <UserCircle className="h-6 w-6" />
                <span className="hidden max-w-[8rem] truncate sm:inline">{user?.username}</span>
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>{user?.email}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => navigate("/settings")}>
                <Gear className="h-4 w-4" />
                {t("nav.settings")}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={handleLogout}>
                <SignOut className="h-4 w-4" />
                {t("nav.logout")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>

      {/* Mobile menu overlay — sibling of header to escape its stacking context */}
      {mobileOpen && (
        <div className="animate-fade-in fixed inset-0 top-16 z-50 overflow-y-auto bg-background/95 backdrop-blur md:hidden">
          <nav className="mx-auto max-w-7xl space-y-1 px-4 pt-2 pb-8">
            <NavLink to="/" end className={mobileLinkClass} onClick={closeMobile}>
              <House className="h-5 w-5" weight="duotone" />
              {t("nav.dashboard")}
            </NavLink>
            <NavLink to="/recommendations" className={mobileLinkClass} onClick={closeMobile}>
              <Sparkle className="h-5 w-5" weight="duotone" />
              {t("nav.recommendations")}
            </NavLink>
            {user?.is_superuser && (
              <NavLink to="/admin" className={mobileLinkClass} onClick={closeMobile}>
                <Shield className="h-5 w-5" weight="duotone" />
                {t("nav.admin")}
              </NavLink>
            )}

            <div className="my-3 h-px bg-border" />

            <button
              type="button"
              className="flex w-full items-center gap-3 rounded-lg px-4 py-3 text-base font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
              onClick={mobileItemClick("/upload")}
            >
              <UploadSimple className="h-5 w-5" weight="duotone" />
              {t("upload.fromFile")}
            </button>
            <button
              type="button"
              className="flex w-full items-center gap-3 rounded-lg px-4 py-3 text-base font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
              onClick={mobileItemClick("/bulk-upload")}
            >
              <Files className="h-5 w-5" weight="duotone" />
              {t("nav.bulkUpload")}
            </button>
            <button
              type="button"
              className="flex w-full items-center gap-3 rounded-lg px-4 py-3 text-base font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
              onClick={mobileItemClick("/upload?tab=spotify")}
            >
              <ListPlus className="h-5 w-5" weight="duotone" />
              {t("upload.fromSpotify")}
            </button>

            <div className="my-3 h-px bg-border" />

            <div className="flex items-center gap-4 px-4 py-3">
              <LanguageSwitcher />
              <ThemeToggle />
            </div>

            <div className="my-3 h-px bg-border" />

            <button
              type="button"
              className="flex w-full items-center gap-3 rounded-lg px-4 py-3 text-base font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
              onClick={mobileItemClick("/settings")}
            >
              <Gear className="h-5 w-5" weight="duotone" />
              {t("nav.settings")}
            </button>
            <button
              type="button"
              className="flex w-full items-center gap-3 rounded-lg px-4 py-3 text-base font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
              onClick={handleLogout}
            >
              <SignOut className="h-5 w-5" weight="duotone" />
              {t("nav.logout")}
            </button>
          </nav>
        </div>
      )}
    </>
  );
}
