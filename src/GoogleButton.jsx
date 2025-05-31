import { useGoogleLogin } from "@react-oauth/google";
import { useState } from "react";

const GoogleSignInButton = () => {
  const [isLoading, setIsLoading] = useState(false);

  const login = useGoogleLogin({
  onSuccess: async (tokenResponse) => {
    const accessToken = tokenResponse.access_token;

    // Save token (optional)
    localStorage.setItem("google_token", accessToken);

    const url = 'https://cautious-waffle-g459gw4qqx55hvvgx-5000.app.github.dev/user';

    try {
      const res = await fetch(url, {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${accessToken}`,  // Send token to backend
        },
      });

      if (!res.ok) {
        throw new Error('Failed to fetch user data');
      }

      const userData = await res.json();
      console.log('User data:', userData);
      setIsLoading(false);
      alert('Yes, it works!');
    } catch (err) {
      console.error('Fetch error:', err);
      alert('Failed to fetch user data');
    }
  },
  onError: () => {
    console.error("Google login failed");
  },
  flow: "implicit",
});

  return (
    <>
      <style>
        {`
          .bottom-border-animation {
            position: absolute;
            bottom: 0;
            left: 0;
            width: 100%;
            height: 2px;
            background: transparent;
            overflow: hidden;
          }

          .bottom-border-animation::before {
            content: '';
            position: absolute;
            width: 50%; /* Smaller segment for Google-like effect */
            height: 100%;
            background: linear-gradient(90deg, #4361EE, #4361EE); /* Indigo gradient */
            animation: googleSlide 1.2s infinite ease-in; /* Infinite looping */
          }

          @keyframes googleSlide {
            0% {
              transform: translateX(-100%);
              opacity: 0.7;
            }
            20% {
              transform: translateX(0%);
              opacity: 1;
            }
            40% {
              transform: translateX(35%);
              opacity: 1;
            }
            50% {
              transform: translateX(50%);
              opacity: 0.7;
            }
            60% {
              transform: translateX(80%);
              opacity: 1;
            }
            80% {
              transform: translateX(100%);
              opacity: 1;
            }
            100% {
              transform: translateX(180%);
              opacity: 0.7;
            }
          }
        `}
      </style>
      <div className="w-full max-w-full sm:max-w-sm md:max-w-md mx-auto animate-fade-in-up">
        <button
          id="google-signup"
          className={`relative w-full flex items-center justify-center bg-white dark:bg-gray-800 border border-gray-500 dark:border-gray-600 rounded-lg py-3 sm:py-3.5 shadow-md hover:shadow-lg hover:bg-indigo-50 dark:hover:bg-gray-700 hover:scale-105 transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:focus:ring-indigo-400 ${
            isLoading ? "opacity-70 cursor-not-allowed" : ""
          }`}
          tabIndex="0"
          onClick={() => {
            setIsLoading(true);
            setTimeout(() => {
              setIsLoading(false);
              login();
            }, 2000);
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
          {isLoading && <div className="bottom-border-animation"></div>}
          <div className="absolute inset-0 bg-indigo-500 opacity-0 hover:opacity-10 rounded-lg transition-opacity duration-300"></div>
        </button>
      </div>
    </>
  );
};

export default GoogleSignInButton;


