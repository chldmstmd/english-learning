import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AdminRoute } from "./components/AdminRoute";
import { ProtectedRoute } from "./components/ProtectedRoute";
import AdminPage from "./pages/AdminPage";
import ArticleListPage from "./pages/ArticleListPage";
import ArticleReaderPage from "./pages/ArticleReaderPage";
import BookDetailPage from "./pages/BookDetailPage";
import VocabListPage from "./pages/VocabListPage";
import LibraryPage from "./pages/LibraryPage";
import LibraryReaderPage from "./pages/LibraryReaderPage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/" element={<ProtectedRoute><ArticleListPage /></ProtectedRoute>} />
        <Route path="/articles/:id" element={<ProtectedRoute><ArticleReaderPage /></ProtectedRoute>} />
        <Route path="/books/:id" element={<ProtectedRoute><BookDetailPage /></ProtectedRoute>} />
        <Route path="/vocab" element={<ProtectedRoute><VocabListPage /></ProtectedRoute>} />
        <Route path="/library" element={<ProtectedRoute><LibraryPage /></ProtectedRoute>} />
        <Route path="/library/:id" element={<ProtectedRoute><LibraryReaderPage /></ProtectedRoute>} />
        <Route path="/admin" element={<AdminRoute><AdminPage /></AdminRoute>} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </BrowserRouter>
  );
}
