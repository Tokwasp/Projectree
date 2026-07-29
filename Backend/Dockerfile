FROM eclipse-temurin:21-jre
WORKDIR /app

# Jenkins가 이미 빌드해둔 jar 파일만 컨테이너로 복사
COPY build/libs/*.jar app.jar

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]