import { useTheme } from "./Theme";

function App() {

  const {toggleTheme} = useTheme()

  return (
    <>
      <button
        onClick={toggleTheme} 
        className="w-12 h-12 flex items-center justify-center  rounded-full  dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors duration-300 shadow-md">
        click
      </button>
    </>
  );
}

export default App;
