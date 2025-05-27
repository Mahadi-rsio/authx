import { useEffect } from "react";
import { useContext } from "react";
import { useState } from "react";
import { createContext } from "react";

const ThemeContext = createContext();

function Theme({ children }) {
  const isDarkMode = window.matchMedia("(prefers-color-scheme : dark)").matches;

  const [theme, setTheme] = useState(isDarkMode ? "dark" : "light");
  useEffect(() => {
    if (localStorage.getItem("system_theme_of_auth_manager")) {
      document.documentElement.setAttribute(
        "data-theme",
        localStorage.getItem("system_theme_of_auth_manager"),
      );
    } else {
      document.documentElement.setAttribute("data-theme", theme);
    }
  }, [theme]);

  const toggleTheme = () => {
    if (theme === "dark") {
      setTheme("light");
      if (!localStorage.getItem("system_theme_of_auth_manager")) {
        localStorage.setItem("system_theme_of_auth_manager", theme);
      } else {
        localStorage.removeItem("system_theme_of_auth_manager");
        localStorage.setItem("system_theme_of_auth_manager", theme);
      }
    }
    if (theme === "light") {
      setTheme("dark");
      if (!localStorage.getItem("system_theme_of_auth_manager")) {
        localStorage.setItem("system_theme_of_auth_manager", theme);
      } else {
        localStorage.removeItem("system_theme_of_auth_manager");
        localStorage.setItem("system_theme_of_auth_manager", theme);
      }
    }
  };

  return (
    <ThemeContext.Provider value={{ toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export default Theme;

//Hook for use theme handler
export const useTheme = () => useContext(ThemeContext)
