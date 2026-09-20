import { BrowserRouter, Routes, Route } from "react-router-dom";

import Home from "./pages/Home";
import PlacePage from "./pages/PlacePage";

function App() {
    return (
        <BrowserRouter>
            <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/place/:placeId" element={<PlacePage />} />
            </Routes>
        </BrowserRouter>
    );
}

export default App;