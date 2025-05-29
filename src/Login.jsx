import { useState, useEffect } from "react";
import { useTheme } from "./Theme";
import { BsMoon, BsSun } from "react-icons/bs";
import { useGoogleLogin } from "@react-oauth/google";

function Login() {
  const [isLoading, setIsLoading] = useState(false);
  const [currentFeatureIndex, setCurrentFeatureIndex] = useState(0);
  const { theme, toggleTheme } = useTheme();
  const [username, setUsername] = useState('')

  // ✅ Correct usage of useGoogleLogin
  const login = useGoogleLogin({
    onSuccess: (tokenResponse) => {
      localStorage.setItem("google_token", JSON.stringify(tokenResponse));
      
      setIsLoading(false)
    },
    onError: () => {
      console.error("Google login failed");
    },
    flow: "implicit",
  });

  const features = [
    {
      icon: (
        <svg className="w-7 h-7 text-indigo-600" fill="currentColor" viewBox="0 0 20 20">
          <path d="M13 7H7v6h6V7zm-3 7a2 2 0 100-4 2 2 0 000 4zm7-7h-2v6h2V7zm-4 8H7a1 1 0 01-1-1v-1h6v1a1 1 0 01-1 1z" />
        </svg>
      ),
      title: "Collaboration",
      desc: "Work seamlessly with teams worldwide.",
    },
    {
      icon: (
        <svg className="w-7 h-7 text-indigo-600" fill="currentColor" viewBox="0 0 20 20">
          <path d="M10 2a8 8 0 00-8 8c0 3.86 2.73 7.07 6.4 7.8a1 1 0 001.2-.8l.4-2a1 1 0 00-.6-1.1A4 4 0 016 10a4 4 0 018 0 4 4 0 01-3.4 3.9 1 1 0 00-.6 1.1l.4 2a1 1 0 001.2.8A8 8 0 0010 2z" />
        </svg>
      ),
      title: "Networking",
      desc: "Connect with industry leaders.",
    },
    {
      icon: (
        <svg className="w-7 h-7 text-indigo-600" fill="currentColor" viewBox="0 0 20 20">
          <path d="M10 2a8 8 0 00-8 8c0 4.42 3.58 8 8 8s8-3.58 8-8a8 8 0 00-8-8zm0 12l-4-4h3V6h2v4h3l-4 4z" />
        </svg>
      ),
      title: "Growth",
      desc: "Unlock new opportunities daily.",
    },
  ];

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentFeatureIndex((prevIndex) => (prevIndex + 1) % features.length);
    }, 3500);
    return () => clearInterval(interval);
  }, [features.length]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gray-50 dark:bg-gray-900 px-4 sm:px-6 lg:px-8 transition-colors duration-500 relative">
      {/* Theme Toggle Button */}
      <div className="absolute top-4 right-4 sm:top-6 sm:right-6 z-50">
        <button
          onClick={toggleTheme}
          className="w-12 h-12 flex items-center justify-center rounded-full bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors duration-300 shadow-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:focus:ring-indigo-400"
          aria-label="Toggle theme"
        >
          {theme === "dark" ? (
            <BsSun className="text-2xl text-yellow-400" />
          ) : (
            <BsMoon className="text-2xl text-blue-300" />
          )}
        </button>
      </div>

      {/* Hero Section */}
      <div className="text-center mb-8 sm:mb-10 max-w-2xl animate-fade-in">
        <img
          src="/a.svg"
          alt="Community Illustration"
          className="w-full max-w-[180px] sm:max-w-[220px] md:max-w-[300px] mx-auto"
        />
        <h1 className="mt-4 sm:mt-6 text-2xl sm:text-3xl md:text-4xl font-inter font-bold text-gray-900 dark:text-white">
          Join with Our Community
        </h1>
        <p className="mt-2 text-sm sm:text-base md:text-lg text-gray-600 dark:text-gray-300">
          Collaborate with over 15,000 professionals and elevate your experience.
        </p>
      </div>
          <h>{username}</h>
      {/* Feature Highlight */}
      <div className="w-full max-w-full sm:max-w-sm md:max-w-md mx-auto mb-8 sm:mb-12 group">
        <div
          key={currentFeatureIndex}
          className="p-5 bg-white dark:bg-gray-800 rounded-xl shadow-md hover:shadow-lg hover:shadow-indigo-200/50 dark:hover:shadow-indigo-500/20 transition-all duration-500 animate-feature-fade"
        >
          <div className="flex justify-center mb-3">
            {features[currentFeatureIndex].icon}
          </div>
          <h3 className="text-base sm:text-lg font-inter font-semibold text-gray-900 dark:text-white text-center">
            {features[currentFeatureIndex].title}
          </h3>
          <p className="mt-2 text-sm sm:text-base text-gray-600 dark:text-gray-300 text-center">
            {features[currentFeatureIndex].desc}
          </p>
        </div>
      </div>

      {/* Google Sign-up Button */}
      <div className="w-full max-w-full sm:max-w-sm md:max-w-md mx-auto animate-fade-in-up">
        <button
          id="google-signup"
          className="relative w-full flex items-center justify-center bg-white dark:bg-gray-800 border border-gray-500 dark:border-gray-600 rounded-lg py-3 sm:py-3.5 shadow-md hover:shadow-lg hover:bg-indigo-50 dark:hover:bg-gray-700 hover:scale-105 transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:focus:ring-indigo-400"
          tabIndex="0"
          onClick={() => {
            setIsLoading(true);
            login();
          }}
          disabled={isLoading}
          aria-label="Sign in with Google"
        >
          <img
            src="https://www.svgrepo.com/show/355037/google.svg"
            alt="Google Icon"
            className="w-5 h-5 sm:w-6 sm:h-6 mr-2 sm:mr-3"
          />
          <span className="text-gray-900 dark:text-gray-100 font-inter font-medium text-sm sm:text-base">
            Sign in with Google
          </span>
          {isLoading && (
            <div
              className="ml-2 sm:ml-3 border-t-2 border-indigo-500 border-solid rounded-full w-4 h-4 sm:w-5 sm:h-5 animate-spin"
              aria-hidden="true"
            ></div>
          )}
          <div className="absolute inset-0 bg-indigo-500 opacity-0 hover:opacity-10 rounded-lg transition-opacity duration-300"></div>
        </button>
      </div>

      {/* Testimonial Carousel */}
      <div className="mt-8 sm:mt-12 w-full max-w-full sm:max-w-sm md:max-w-md mx-auto group animate-fade-in-up">
        <div className="relative overflow-hidden">
          <div className="flex group-hover:pause-animation animate-slide">
            {[
              {
                quote: "A seamless platform for professional collaboration.",
                author: "Alex, Product Manager",
              },
              {
                quote: "Streamlined my workflow and connections.",
                author: "Sam, Software Engineer",
              },
              {
                quote: "The best tool for networking and growth.",
                author: "Taylor, Marketing Lead",
              },
            ].map((testimonial, index) => (
              <div key={index} className="flex-shrink-0 w-full text-center px-4">
                <p className="text-sm sm:text-base text-gray-600 dark:text-gray-300">
                  "{testimonial.quote}"
                </p>
                <p className="mt-2 text-xs sm:text-sm font-medium text-gray-700 dark:text-gray-200">
                  — {testimonial.author}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="mt-8 sm:mt-12 text-center animate-fade-in-up">
        <div className="flex flex-col sm:flex-row justify-center gap-4 sm:gap-6 mb-4">
          <div className="flex flex-col items-center justify-center">
            <div className="flex items-center">
              <svg className="w-5 h-5 sm:w-6 sm:h-6 text-indigo-600 mr-2" fill="currentColor" viewBox="0 0 20 20">
                <path d="M10 2a8 8 0 100 16 8 8 0 000-16zm1 11.93V12H9v1.93A5.986 5.986 0 014 8h2v2h2V8h4v2h2a5.986 5.986 0 01-5 5.93z" />
              </svg>
              <span className="text-sm sm:text-base text-gray-600 dark:text-gray-300">
                15K+ Professionals
              </span>
            </div>
            <div className="w-full max-w-[120px] h-1.5 bg-gray-200 dark:bg-gray-700 mt-2 rounded-full">
              <div className="h-full bg-indigo-600 rounded-full animate-progress" style={{ width: "75%" }}></div>
            </div>
          </div>

          <div className="flex flex-col items-center justify-center">
            <div className="flex items-center">
              <svg className="w-5 h-5 sm:w-6 sm:h-6 text-indigo-600 mr-2" fill="currentColor" viewBox="0 0 20 20">
                <path d="M10 2a8 8 0 100 16 8 8 0 000-16zm3.36 5.64l-4 4a1 1 0 01-1.42 0l-2-2a1 1 0 011.42-1.42L9 9.83l3.36-3.36a1 1 0 011.42 1.42z" />
              </svg>
              <span className="text-sm sm:text-base text-gray-600 dark:text-gray-300">
                99% Satisfaction
              </span>
            </div>
            <div className="w-full max-w-[120px] h-1.5 bg-gray-200 dark:bg-gray-700 mt-2 rounded-full">
              <div className="h-full bg-indigo-600 rounded-full animate-progress" style={{ width: "99%" }}></div>
            </div>
          </div>
        </div>
        <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">
          Trusted by professionals worldwide.{" "}
          <a href="/terms" className="underline hover:text-indigo-600 transition duration-200">
            Terms
          </a>{" "}
          &{" "}
          <a href="/privacy" className="underline hover:text-indigo-600 transition duration-200">
            Privacy
          </a>
        </p>
      </footer>
    </div>
  );
}

export default Login;