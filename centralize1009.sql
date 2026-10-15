-- MySQL dump 10.13  Distrib 8.0.46, for Win64 (x86_64)
--
-- Host: 127.0.0.1    Database: centralized_database
-- ------------------------------------------------------
-- Server version	8.0.46

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `accounts`
--

DROP TABLE IF EXISTS `accounts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `accounts` (
  `account_id` int NOT NULL AUTO_INCREMENT,
  `fullname` varchar(150) NOT NULL,
  `email` varchar(150) NOT NULL,
  `password` varchar(255) NOT NULL,
  `role` enum('owner','customer','caretaker') NOT NULL,
  `account_status` enum('Active','Inactive','Suspended') DEFAULT 'Active',
  `is_verified` tinyint(1) DEFAULT '0',
  `verification_code` varchar(10) DEFAULT NULL,
  `verification_expiration` datetime DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `approval_status` enum('Pending','Approved','Rejected') DEFAULT 'Pending',
  `approved_by` int DEFAULT NULL,
  `approved_at` datetime DEFAULT NULL,
  `requested_resort_id` int DEFAULT NULL,
  PRIMARY KEY (`account_id`),
  UNIQUE KEY `email` (`email`),
  KEY `fk_requested_resort` (`requested_resort_id`),
  CONSTRAINT `fk_requested_resort` FOREIGN KEY (`requested_resort_id`) REFERENCES `resorts` (`resort_id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=21 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `accounts`
--

LOCK TABLES `accounts` WRITE;
/*!40000 ALTER TABLE `accounts` DISABLE KEYS */;
INSERT INTO `accounts` VALUES (1,'Test Caretaker','caretaker@test.com','scrypt:32768:8:1$Tn6M5cB5P6Y3T8sA$e46dcb6d89b4c0d8d5f3f92a9c8b8e7d4f1b4a5d4d9a3b2c1d6e5f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6','caretaker','Active',1,NULL,NULL,'2026-08-06 04:51:00','Approved',NULL,'2026-08-06 12:51:00',NULL),(4,'Aron-John Castillo','aronjohncastillo098@gmail.com','scrypt:32768:8:1$V2hQlZHQCxRNI5IX$e2036475fd1f6e9fa0501561ca29542bea32527702382c56d5dec58757175714d249e96dcc1ae847163f824126ec71b6795f9d4d23580fbdc7407de458edb8e8','customer','Active',1,NULL,NULL,'2026-08-06 04:57:00','Pending',NULL,NULL,NULL),(9,'Owner One','owner1@pansol.com','scrypt:32768:8:1$V2hQlZHQCxRNI5IX$e2036475fd1f6e9fa0501561ca29542bea32527702382c56d5dec58757175714d249e96dcc1ae847163f824126ec71b6795f9d4d23580fbdc7407de458edb8e8','owner','Active',1,NULL,NULL,'2026-08-08 04:42:36','Approved',NULL,NULL,NULL),(10,'Owner Two','owner2@pansol.com','REPLACE_WITH_REAL_HASH_2','owner','Active',1,NULL,NULL,'2026-08-08 04:42:36','Approved',NULL,NULL,NULL),(11,'Owner Three','owner3@pansol.com','REPLACE_WITH_REAL_HASH_3','owner','Active',1,NULL,NULL,'2026-08-08 04:42:36','Approved',NULL,NULL,NULL),(12,'Aron-John Castillo','atcastillsso@ccc.edu.ph','scrypt:32768:8:1$7dK9mP2xQwR4tY8z$4f4c3f6c1d3e3d9b5f5c0d8e6a9f8c6d3e7b5f4a1c2d9e8f7b6c5d4e3f2a1b0','caretaker','Active',1,NULL,NULL,'2026-08-08 04:44:44','Approved',9,'2026-08-08 13:13:43',NULL),(13,'Aron-John Castillo','atcastillso@ccc.edu.ph','scrypt:32768:8:1$IkfWlj4cjukzZpzf$c80cdf3dc92645bf19e47dc90e780e191ea87dcf336435973fb529b131c221320a60d852fb7145716d348d74bb54b623a947ddb1ecbed658330c72c991631542','customer','Active',0,'728935','2026-08-08 19:31:16','2026-08-08 11:26:15','Pending',NULL,NULL,NULL),(14,'Aron-John Castillo','atcastilslo@ccc.edu.ph','scrypt:32768:8:1$trmHBq2kDH0giFNo$30a774bc15195319a6aef542a5e1dfd59fb6bbbaf584a27d950b12968606529262f5f617805ccb4b0f6d12595aba2907b795fe3ed14e2324b41bc7e3ffeccf33','customer','Active',1,NULL,NULL,'2026-08-08 11:29:55','Pending',NULL,NULL,NULL),(15,'Aron-John Castillo','aronjohncastilloo098@gmail.com','scrypt:32768:8:1$V7IKLcdAhOrPxs69$28b4e94768caebfb15379896f0c9c7267c826bd9e450d32e55fafc170e3f697042521cc003877266dd4c7031ac6d9ae323b0589899219c4bdefd33768ad595d3','customer','Active',1,NULL,NULL,'2026-08-12 11:58:45','Pending',NULL,NULL,NULL),(16,'Aron-John Castillo','aronjohncastillooo098@gmail.com','scrypt:32768:8:1$rgDu5KZzddOxpNQS$9667337dab3da5ab0cff9a9ee963ac333d677736744a92bbae4aa2a694eef9d734584675f3646464086c68902138729bb5a4155a701825e37ec3aa44eb0f1a60','caretaker','Active',1,NULL,NULL,'2026-08-12 12:10:04','Approved',9,'2026-08-12 20:10:40',NULL),(17,'Aron-John Castillo','aronjohncastilloa098@gmail.com','scrypt:32768:8:1$i4BrAP7Bbc6IjGAv$a6a91ca139cfbdf461db33d8a107597138be282fa512444733f53b819233b1050f6b8ed9a5b4df00519073c4cfd95d1f806db62c1674ee8781be47b88bf3b175','caretaker','Active',1,NULL,NULL,'2026-09-16 13:15:51','Approved',9,'2026-09-16 21:22:42',NULL),(18,'Aron-John Castillo','aronjohncastilloaa098@gmail.com','scrypt:32768:8:1$SlovljVBXID4jT0F$0a0be48ba231756befa7e1ce03a573a8a2613f7a719d078fbf6af6bc8c43e2c532d9be09018e98a9dcccbce0e54c30969aabbcc3905c453b994f48cb9fea7e12','caretaker','Active',1,NULL,NULL,'2026-09-16 14:07:07','Approved',9,'2026-09-16 22:07:21',NULL),(19,'Aron-John Castillo','aronjohncastilla098@gmail.com','scrypt:32768:8:1$sM3YKRYq0nQCbR5W$a21b1b05a830f5583281d5f1bd21c93aaa7b95fd10b3e8f79ea019498b4ce27469cce758faae1ba276d33a92df3d7bd6f2d64597ec2f4fb28a42598ad8e06693','caretaker','Active',1,NULL,NULL,'2026-09-17 03:47:59','Approved',9,'2026-09-17 11:47:59',NULL),(20,'Walk-in Guest','walkin.guest@pansolresorts.com','scrypt:32768:8:1$JYp5QvFFEuz1gvuf$e5cc52b7e534d082f60cf0e25231b0920cac03241db2fcd65d11186d1377249c5a8839a2add3802526733a90cd49797657ddcf8d485a500fab6bd06972c2745d','customer','Active',1,NULL,NULL,'2026-10-01 03:36:30','Approved',NULL,NULL,NULL);
/*!40000 ALTER TABLE `accounts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `caretakers`
--

DROP TABLE IF EXISTS `caretakers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `caretakers` (
  `caretaker_id` int NOT NULL AUTO_INCREMENT,
  `account_id` int DEFAULT NULL,
  `resort_id` int NOT NULL,
  `assigned_date` datetime DEFAULT CURRENT_TIMESTAMP,
  `status` enum('Pending','Active','Inactive') DEFAULT 'Pending',
  PRIMARY KEY (`caretaker_id`),
  UNIQUE KEY `account_id` (`account_id`),
  KEY `fk_caretaker_resort` (`resort_id`),
  CONSTRAINT `caretakers_ibfk_1` FOREIGN KEY (`account_id`) REFERENCES `accounts` (`account_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_caretaker_account` FOREIGN KEY (`account_id`) REFERENCES `accounts` (`account_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_caretaker_resort` FOREIGN KEY (`resort_id`) REFERENCES `resorts` (`resort_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `caretakers`
--

LOCK TABLES `caretakers` WRITE;
/*!40000 ALTER TABLE `caretakers` DISABLE KEYS */;
INSERT INTO `caretakers` VALUES (4,12,1,'2026-08-08 12:44:44','Active'),(5,16,2,'2026-08-12 20:10:04','Active'),(6,17,3,'2026-09-16 21:15:52','Active'),(7,18,9,'2026-09-16 22:07:08','Active'),(8,19,10,'2026-09-17 11:47:59','Active');
/*!40000 ALTER TABLE `caretakers` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `customers`
--

DROP TABLE IF EXISTS `customers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `customers` (
  `customer_id` int NOT NULL AUTO_INCREMENT,
  `account_id` int DEFAULT NULL,
  `phone` varchar(20) DEFAULT NULL,
  `email` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`customer_id`),
  UNIQUE KEY `account_id` (`account_id`),
  CONSTRAINT `customers_ibfk_1` FOREIGN KEY (`account_id`) REFERENCES `accounts` (`account_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `customers`
--

LOCK TABLES `customers` WRITE;
/*!40000 ALTER TABLE `customers` DISABLE KEYS */;
INSERT INTO `customers` VALUES (1,4,'+639913295173','aronjohncastillo098@gmail.com'),(2,13,'(+63) 991 329 5173','atcastillso@ccc.edu.ph'),(3,14,'(+63) 991 329 5173','atcastilslo@ccc.edu.ph'),(4,15,'+639913295173','aronjohncastilloo098@gmail.com'),(5,9,'1919',NULL),(6,18,'+639913295173',NULL),(7,20,NULL,NULL);
/*!40000 ALTER TABLE `customers` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `messages`
--

DROP TABLE IF EXISTS `messages`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `messages` (
  `message_id` int NOT NULL AUTO_INCREMENT,
  `sender_account` int NOT NULL,
  `receiver_account` int NOT NULL,
  `message` text,
  `is_read` tinyint(1) DEFAULT '0',
  `sent_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`message_id`),
  KEY `sender_account` (`sender_account`),
  KEY `receiver_account` (`receiver_account`),
  CONSTRAINT `messages_ibfk_1` FOREIGN KEY (`sender_account`) REFERENCES `accounts` (`account_id`),
  CONSTRAINT `messages_ibfk_2` FOREIGN KEY (`receiver_account`) REFERENCES `accounts` (`account_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `messages`
--

LOCK TABLES `messages` WRITE;
/*!40000 ALTER TABLE `messages` DISABLE KEYS */;
/*!40000 ALTER TABLE `messages` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `notifications`
--

DROP TABLE IF EXISTS `notifications`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `notifications` (
  `notification_id` int NOT NULL AUTO_INCREMENT,
  `account_id` int NOT NULL,
  `title` varchar(255) DEFAULT NULL,
  `message` text,
  `type` varchar(50) DEFAULT NULL,
  `is_read` tinyint(1) DEFAULT '0',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`notification_id`),
  KEY `account_id` (`account_id`),
  CONSTRAINT `notifications_ibfk_1` FOREIGN KEY (`account_id`) REFERENCES `accounts` (`account_id`)
) ENGINE=InnoDB AUTO_INCREMENT=15 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `notifications`
--

LOCK TABLES `notifications` WRITE;
/*!40000 ALTER TABLE `notifications` DISABLE KEYS */;
INSERT INTO `notifications` VALUES (1,15,'Reservation approved','Your reservation #RSV-8 has been approved.','reservation_approved',1,'2026-09-11 08:40:29'),(2,9,'Reservation approved','Your reservation #RSV-7 has been approved.','reservation_approved',1,'2026-09-16 12:42:12'),(3,18,'Reservation approved','Your reservation #RSV-9 was approved by the caretaker.','reservation_approved',0,'2026-09-16 14:13:58'),(4,1,'Walk-in booking awaiting verification','aron: walk-in booking #RSV-15 for Aron-John Castillo (PHP 0.01) needs your approval.','walkin_pending',0,'2026-10-01 03:00:46'),(5,4,'Walk-in booking recorded','Your walk-in booking #RSV-15 at aron (PHP 0.01) was recorded and is awaiting admin verification.','walkin_pending',0,'2026-10-01 03:00:46'),(6,1,'Walk-in booking awaiting verification','aron: walk-in booking #RSV-16 for Aron-John Castillo (PHP 2,000.00), booked by caretaker Aron-John Castillo, needs your approval.','walkin_pending',0,'2026-10-01 03:36:30'),(7,4,'Reservation rejected','Your reservation #RSV-15 was rejected by the caretaker.','reservation_rejected',0,'2026-10-01 03:36:38'),(8,20,'Reservation approved','Your reservation #RSV-16 was approved by the caretaker.','reservation_approved',0,'2026-10-01 03:36:41'),(9,1,'Walk-in booking awaiting verification','aron: walk-in booking #RSV-17 for fadas (PHP 1,010.00), booked by caretaker Aron-John Castillo, needs your approval.','walkin_pending',0,'2026-10-01 04:01:02'),(10,9,'Walk-in booking awaiting verification','aron: walk-in booking #RSV-18 for fadassadada (PHP 5,000.00), booked by caretaker Aron-John Castillo, needs your approval.','walkin_pending',0,'2026-10-01 04:22:51'),(11,9,'Maintenance request: aircon','Resort: aron | Location: room2 | Priority: Normal | Reported by: Aron-John Castillo\nsdada','maintenance_request',1,'2026-10-01 04:23:16'),(12,20,'Reservation approved','Your reservation #RSV-18 has been approved.','reservation_approved',0,'2026-10-01 04:24:16'),(13,9,'Walk-in booking awaiting verification','aron: walk-in booking #RSV-19 for aronjohn (PHP 2,000.00), booked by caretaker Aron-John Castillo, needs your approval.','walkin_pending',0,'2026-10-05 01:28:30'),(14,20,'Reservation approved','Your reservation #RSV-19 has been approved.','reservation_approved',0,'2026-10-05 01:29:07');
/*!40000 ALTER TABLE `notifications` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `owners`
--

DROP TABLE IF EXISTS `owners`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `owners` (
  `owner_id` int NOT NULL AUTO_INCREMENT,
  `account_id` int DEFAULT NULL,
  PRIMARY KEY (`owner_id`),
  UNIQUE KEY `account_id` (`account_id`),
  CONSTRAINT `owners_ibfk_1` FOREIGN KEY (`account_id`) REFERENCES `accounts` (`account_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `owners`
--

LOCK TABLES `owners` WRITE;
/*!40000 ALTER TABLE `owners` DISABLE KEYS */;
INSERT INTO `owners` VALUES (1,9),(2,10),(3,11);
/*!40000 ALTER TABLE `owners` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `payments`
--

DROP TABLE IF EXISTS `payments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `payments` (
  `payment_id` int NOT NULL AUTO_INCREMENT,
  `reservation_id` int NOT NULL,
  `proof_of_payment` varchar(255) DEFAULT NULL,
  `reference_number` varchar(100) DEFAULT NULL,
  `amount_paid` decimal(10,2) DEFAULT NULL,
  `payment_status` enum('Pending','Verified','Rejected') DEFAULT 'Pending',
  `payment_date` datetime DEFAULT NULL,
  PRIMARY KEY (`payment_id`),
  KEY `reservation_id` (`reservation_id`),
  CONSTRAINT `payments_ibfk_1` FOREIGN KEY (`reservation_id`) REFERENCES `reservations` (`reservation_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `payments`
--

LOCK TABLES `payments` WRITE;
/*!40000 ALTER TABLE `payments` DISABLE KEYS */;
INSERT INTO `payments` VALUES (1,4,'uploads/payments/0e8ff1a3773e4065a380ea7865541154.png',NULL,150.00,'Pending','2026-09-11 15:49:17'),(2,5,'uploads/payments/43c2b63cfca74458a689352e4ffed8de.jpg',NULL,150.00,'Pending','2026-09-11 16:17:08'),(3,6,'uploads/payments/eded620f647c471391f16d489928e039.jpg',NULL,150.00,'Pending','2026-09-11 16:28:41'),(4,7,'uploads/payments/f00826eef991401896bd33057c559dad.png',NULL,150.00,'Verified','2026-09-11 16:33:48'),(5,8,'uploads/payments/8c24bb6964e9444ea061f4675a207f8b.png',NULL,150.00,'Verified','2026-09-11 16:36:06'),(6,9,'uploads/payments/9fb74939b78a48ad817d96222037bcec.png',NULL,0.00,'Verified','2026-09-16 22:12:56'),(7,14,'uploads/payments/f56aae2f6b3b4beca31be2f3da34ea9d.jpg',NULL,1850.00,'Pending','2026-09-28 12:21:37'),(8,15,'uploads/walkin_proofs/12697c73365c478da40a4c9bdb223653.jpg',NULL,0.01,'Rejected','2026-10-01 11:00:46'),(9,16,'uploads/walkin_proofs/8d52b33f1c4347a1927d695ccdb1fbc5.jpg',NULL,2000.00,'Verified','2026-10-01 11:36:30'),(10,17,'uploads/walkin_proofs/f3f71fa7063548fcbb63671db5506ea2.jpg',NULL,1010.00,'Pending','2026-10-01 12:01:02'),(11,18,'uploads/walkin_proofs/a4daeb45bf784bf49d75429f88a69aec.jpg',NULL,5000.00,'Verified','2026-10-01 12:22:51'),(12,19,'uploads/walkin_proofs/26e69e4e637f4a809b1726c3fe6190fc.jpg',NULL,2000.00,'Verified','2026-10-05 09:28:30');
/*!40000 ALTER TABLE `payments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `reservations`
--

DROP TABLE IF EXISTS `reservations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `reservations` (
  `reservation_id` int NOT NULL AUTO_INCREMENT,
  `customer_id` int NOT NULL,
  `resort_id` int NOT NULL,
  `check_in` date DEFAULT NULL,
  `check_out` date DEFAULT NULL,
  `guests` int DEFAULT NULL,
  `total_amount` decimal(10,2) DEFAULT NULL,
  `reservation_status` enum('Pending','Confirmed','Cancelled','Completed','Rejected') DEFAULT 'Pending',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `guest_name` varchar(150) DEFAULT NULL,
  `guest_phone` varchar(20) DEFAULT NULL,
  `pax` int DEFAULT NULL,
  `gas_stove` tinyint(1) DEFAULT '0',
  `booking_source` enum('Online','Walk-in') NOT NULL DEFAULT 'Online',
  PRIMARY KEY (`reservation_id`),
  KEY `customer_id` (`customer_id`),
  KEY `resort_id` (`resort_id`),
  CONSTRAINT `reservations_ibfk_1` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`customer_id`),
  CONSTRAINT `reservations_ibfk_2` FOREIGN KEY (`resort_id`) REFERENCES `resorts` (`resort_id`)
) ENGINE=InnoDB AUTO_INCREMENT=20 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `reservations`
--

LOCK TABLES `reservations` WRITE;
/*!40000 ALTER TABLE `reservations` DISABLE KEYS */;
INSERT INTO `reservations` VALUES (1,4,5,'2026-05-27','2026-05-28',2,0.00,'Pending','2026-09-11 07:03:58',NULL,NULL,NULL,0,'Online'),(2,4,5,'2026-05-27','2026-05-28',2,0.00,'Pending','2026-09-11 07:13:12',NULL,NULL,NULL,0,'Online'),(3,4,5,'2026-05-27','2026-05-28',2,0.00,'Pending','2026-09-11 07:21:12',NULL,NULL,NULL,0,'Online'),(4,4,5,'2026-05-08','2026-05-09',1,150.00,'Pending','2026-09-11 07:48:37','Aron-John Castillo','09196281147',1,1,'Online'),(5,4,4,'2026-05-28','2026-05-29',3,150.00,'Pending','2026-09-11 08:17:01','dadsd','09196281147',3,1,'Online'),(6,5,5,'2026-05-01','2026-05-02',1,150.00,'Pending','2026-09-11 08:28:34','dadsd','125919',1,1,'Online'),(7,5,5,'2026-05-21','2026-05-22',2,150.00,'Confirmed','2026-09-11 08:33:42','adadf','1919',2,1,'Online'),(8,4,5,'2026-05-15','2026-05-16',12,150.00,'Confirmed','2026-09-11 08:35:55','adadf','121121',12,1,'Online'),(9,6,9,'2026-09-19','2026-09-20',20,0.00,'Confirmed','2026-09-16 14:12:33','Aron-John Castillo','+639913295173',20,0,'Online'),(10,4,5,'2026-10-01','2026-10-02',15,1650.00,'Pending','2026-09-28 03:42:57','Aron-John Castillo','+639913295173',15,1,'Online'),(11,4,5,'2026-10-02','2026-10-03',15,1700.00,'Pending','2026-09-28 03:43:40','Aron-John Castillo','+639913295173',15,1,'Online'),(12,4,5,'2026-10-03','2026-10-04',15,1650.00,'Pending','2026-09-28 03:50:45','Aron-John Castillo','+639913295173',15,1,'Online'),(13,4,5,'2026-10-04','2026-10-05',15,1500.00,'Pending','2026-09-28 03:54:01','Aron-John Castillo','+639913295173',15,0,'Online'),(14,4,5,'2026-10-05','2026-10-06',16,1850.00,'Pending','2026-09-28 04:21:10','Aron-John Castillo','+639913295173',16,1,'Online'),(15,1,10,'2026-10-02','2026-10-03',20,0.01,'Rejected','2026-10-01 03:00:46','Aron-John Castillo',NULL,NULL,0,'Walk-in'),(16,7,10,'2026-10-01','2026-10-02',20,2000.00,'Confirmed','2026-10-01 03:36:30','Aron-John Castillo (09196281147)',NULL,NULL,0,'Walk-in'),(17,7,10,'2026-10-01','2026-10-02',10,1010.00,'Pending','2026-10-01 04:01:02','fadas (09196281147)',NULL,NULL,0,'Walk-in'),(18,7,10,'2026-10-03','2026-10-04',2,5000.00,'Confirmed','2026-10-01 04:22:51','fadassadada (09196281147)',NULL,NULL,0,'Walk-in'),(19,7,10,'2026-10-05','2026-10-06',200,2000.00,'Confirmed','2026-10-05 01:28:30','aronjohn (09196281147)',NULL,NULL,0,'Walk-in');
/*!40000 ALTER TABLE `reservations` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `resorts`
--

DROP TABLE IF EXISTS `resorts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `resorts` (
  `resort_id` int NOT NULL AUTO_INCREMENT,
  `owner_id` int NOT NULL,
  `caretaker_id` int DEFAULT NULL,
  `resort_name` varchar(150) NOT NULL,
  `address` text,
  `description` text,
  `email` varchar(150) DEFAULT NULL,
  `phone` varchar(20) DEFAULT NULL,
  `logo` varchar(255) DEFAULT NULL,
  `amenities` text,
  `status` enum('Active','Inactive') DEFAULT 'Active',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `price` decimal(10,2) DEFAULT NULL,
  `max_pax` int DEFAULT NULL,
  PRIMARY KEY (`resort_id`),
  KEY `owner_id` (`owner_id`),
  KEY `caretaker_id` (`caretaker_id`),
  CONSTRAINT `resorts_ibfk_1` FOREIGN KEY (`owner_id`) REFERENCES `owners` (`owner_id`),
  CONSTRAINT `resorts_ibfk_2` FOREIGN KEY (`caretaker_id`) REFERENCES `caretakers` (`caretaker_id`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `resorts`
--

LOCK TABLES `resorts` WRITE;
/*!40000 ALTER TABLE `resorts` DISABLE KEYS */;
INSERT INTO `resorts` VALUES (1,1,NULL,'TRIPLE Z RESORT',NULL,NULL,NULL,NULL,NULL,NULL,'Active','2026-08-08 04:42:36',1100.00,12),(2,1,NULL,'SUNSCAPE RESORT','Purok 6, Brgy Buycal Calamba City',NULL,'aronjohncastillo098@gmail.com','09913295173',NULL,NULL,'Active','2026-08-08 04:42:36',1300.00,18),(3,2,NULL,'LUCKY MIELS RESORT',NULL,NULL,NULL,NULL,NULL,NULL,'Active','2026-08-08 04:42:36',1200.00,15),(4,2,NULL,'MAGIC KINGDOM RESORT',NULL,NULL,NULL,NULL,NULL,NULL,'Active','2026-08-08 04:42:36',1500.00,20),(5,3,NULL,'GALLELY RESORT',NULL,NULL,NULL,NULL,NULL,NULL,'Active','2026-08-08 04:42:36',1500.00,15),(6,3,NULL,'RENALYN RESORT',NULL,NULL,NULL,NULL,NULL,NULL,'Active','2026-08-08 04:42:36',1200.00,15),(9,1,NULL,'Luckymiels Private Pool Resort','Block 8 Lot 15 Almond Street, Indigo Bay Subdivision, Bagong Kalsada','Pogi si Aron','aronjohncastillo098@gmail.com','09913295173',NULL,NULL,'Active','2026-09-16 14:06:34',NULL,NULL),(10,1,NULL,'aron','Purok 6',NULL,'aronjohncastillo098@gmail.com','09913295173',NULL,NULL,'Active','2026-09-17 03:47:30',NULL,NULL);
/*!40000 ALTER TABLE `resorts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `reviews`
--

DROP TABLE IF EXISTS `reviews`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `reviews` (
  `review_id` int NOT NULL AUTO_INCREMENT,
  `customer_id` int NOT NULL,
  `resort_id` int NOT NULL,
  `rating` int DEFAULT NULL,
  `comment` text,
  `review_date` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`review_id`),
  KEY `customer_id` (`customer_id`),
  KEY `resort_id` (`resort_id`),
  CONSTRAINT `reviews_ibfk_1` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`customer_id`),
  CONSTRAINT `reviews_ibfk_2` FOREIGN KEY (`resort_id`) REFERENCES `resorts` (`resort_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `reviews`
--

LOCK TABLES `reviews` WRITE;
/*!40000 ALTER TABLE `reviews` DISABLE KEYS */;
/*!40000 ALTER TABLE `reviews` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-10-09 20:51:42
