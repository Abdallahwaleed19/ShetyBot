-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Host: 127.0.0.1:3307
-- Generation Time: 22 أكتوبر 2026 الساعة 00:16
-- إصدار الخادم: 10.4.32-MariaDB
-- PHP Version: 8.5.10

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `seha_db`
--

-- --------------------------------------------------------

--
-- بنية الجدول `sick_leave_reports`
--

CREATE TABLE `sick_leave_reports` (
  `id` bigint(20) UNSIGNED NOT NULL,
  `service_code` varchar(50) NOT NULL,
  `report_type` varchar(100) NOT NULL,
  `admission_date` date NOT NULL,
  `discharge_date` date NOT NULL,
  `leave_duration_days` smallint(5) UNSIGNED NOT NULL,
  `issue_date` date NOT NULL,
  `report_time` time DEFAULT NULL,
  `national_id` varchar(10) NOT NULL,
  `patient_name_ar` varchar(200) NOT NULL,
  `patient_name_en` varchar(200) DEFAULT NULL,
  `nationality` varchar(100) DEFAULT NULL,
  `employer` varchar(200) DEFAULT NULL,
  `practitioner_name_ar` varchar(200) DEFAULT NULL,
  `practitioner_name_en` varchar(200) DEFAULT NULL,
  `job_title_ar` varchar(200) DEFAULT NULL,
  `job_title_en` varchar(200) DEFAULT NULL,
  `hospital_name_ar` varchar(200) DEFAULT NULL,
  `hospital_name_en` varchar(200) DEFAULT NULL,
  `hospital_type` enum('government','private') DEFAULT NULL,
  `hospital_logo_path` varchar(255) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `companion_name` varchar(255) DEFAULT NULL,
  `relationship` varchar(100) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Indexes for dumped tables
--

--
-- Indexes for table `sick_leave_reports`
--
ALTER TABLE `sick_leave_reports`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `sick_leave_reports_national_id_service_code_unique` (`national_id`,`service_code`),
  ADD UNIQUE KEY `sick_leave_reports_service_code_unique` (`service_code`),
  ADD KEY `sick_leave_reports_national_id_index` (`national_id`);

--
-- AUTO_INCREMENT for dumped tables
--

--
-- AUTO_INCREMENT for table `sick_leave_reports`
--
ALTER TABLE `sick_leave_reports`
  MODIFY `id` bigint(20) UNSIGNED NOT NULL AUTO_INCREMENT;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
